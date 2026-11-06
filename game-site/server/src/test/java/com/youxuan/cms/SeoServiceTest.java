package com.youxuan.cms;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.assertj.core.api.Assertions.assertThat;

class SeoServiceTest {
    final SeoService service = new SeoService(new ObjectMapper());
    Game game() {
        Game g = new Game();
        g.id = "14545"; g.slug = "little-dragon"; g.name = "小小驯龙师";
        g.summary = "收集恐龙，搭配阵容。"; g.description = "游戏介绍正文";
        g.platform = "Android"; g.heroUrl = "/media/hero.jpg";
        g.faqs = List.of(new Game.Faq("怎么领首充奖励？", "需要完成首充。"));
        return g;
    }
    SiteSettings site() {
        SiteSettings s = new SiteSettings();
        s.siteName = "游选"; s.siteUrl = "https://play.example"; s.allowIndexing = true;
        return s;
    }
    @Test void generatesCanonicalAndFallbackSeoFromGameNotRequestHost() throws Exception {
        var seo = service.game(game(), site(), false);
        assertThat(seo.get("title")).contains("小小驯龙师").contains("游选");
        assertThat(seo.get("description")).isEqualTo("收集恐龙，搭配阵容。");
        assertThat(seo.get("canonical")).isEqualTo("https://play.example/games/little-dragon/");
        assertThat(seo.get("image")).isEqualTo("https://play.example/media/hero.jpg");
        assertThat(seo.get("robots")).startsWith("index,");
        var json = new ObjectMapper().readTree(seo.get("jsonLd"));
        assertThat(json.get("@graph").toString()).contains("FAQPage", "VideoGame", "BreadcrumbList");
        assertThat(seo.get("jsonLd")).doesNotContain("aggregateRating", "offers");
    }
    @Test void respectsCustomSeoAndEscapesJsonScriptTerminator() throws Exception {
        Game g = game(); g.seoTitle = "自定义标题"; g.seoDescription = "自定义描述";
        g.description = "</script><script>alert(1)</script>";
        g.seoKeywords = "恐龙,养成";
        var seo = service.game(g, site(), false);
        assertThat(seo.get("title")).isEqualTo("自定义标题");
        assertThat(seo.get("description")).isEqualTo("自定义描述");
        assertThat(seo.get("keywords")).isEqualTo("恐龙,养成");
        assertThat(seo.get("jsonLd")).doesNotContain("</script>");
        new ObjectMapper().readTree(seo.get("jsonLd"));
    }
    @Test void previewUnconfiguredSiteAndExcludedGameNeverIndex() {
        assertThat(service.game(game(), site(), true).get("robots")).startsWith("noindex,");
        SiteSettings settings = site(); settings.siteUrl = "";
        assertThat(service.game(game(), settings, false).get("canonical")).isEmpty();
        assertThat(service.game(game(), settings, false).get("robots")).startsWith("noindex,");
        settings = site(); settings.allowIndexing = false;
        assertThat(service.game(game(), settings, false).get("robots")).startsWith("noindex,");
        Game g = game(); g.noindex = true;
        assertThat(service.game(g, site(), false).get("robots")).startsWith("noindex,");
    }
    @Test void unsafeOrNonRootSiteOriginIsNeverUsed() {
        for (String url : List.of("https://user:secret@evil.test", "javascript:alert(1)", "https://play.example/path", "https://play.example?x=1")) {
            SiteSettings s = site(); s.siteUrl = url;
            assertThat(service.game(game(), s, false).get("canonical")).isEmpty();
            assertThat(service.game(game(), s, false).get("robots")).startsWith("noindex,");
        }
    }
    @Test void searchPagesDoNotCreateDuplicateIndexablePages() {
        assertThat(service.home(site(), true).get("robots")).startsWith("noindex,");
        assertThat(service.home(site(), true).get("canonical")).isEqualTo("https://play.example/");
    }
}
