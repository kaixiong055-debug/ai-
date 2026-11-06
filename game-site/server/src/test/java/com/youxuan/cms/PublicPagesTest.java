package com.youxuan.cms;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import java.util.List;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={
    "spring.datasource.url=jdbc:h2:mem:publicpages;DB_CLOSE_DELAY=-1",
    "cms.admin.password=PublicPageTestOnly-2026",
    "cms.demo.enabled=false",
    "cms.data-dir=${java.io.tmpdir}/cms-public-test"
})
@AutoConfigureMockMvc
class PublicPagesTest {
    @Autowired MockMvc mvc;
    @Autowired GameService games;
    @Autowired JdbcTemplate db;
    @BeforeEach void reset() {
        db.update("DELETE FROM cms_games"); db.update("DELETE FROM cms_settings");
        SiteSettings s = new SiteSettings(); s.siteUrl="https://games.example"; s.allowIndexing=true;
        games.saveSettings(s);
    }
    Game add(boolean published) {
        Game g=new Game(); g.id="14545";g.slug="dragon";g.name="恐龙游戏";g.summary="独立游戏摘要";
        g.description="这是服务端直接生成的完整游戏正文。";g.platform="Android";g.version="1.0.0";
        g.iconUrl="/media/icon.jpg";g.heroUrl="/media/hero.jpg";g.downloadUrl="https://m.3387.com/s/example?d=1";
        g.screenshots=List.of(new Game.Picture("/media/shot.jpg","恐龙进化画面"));
        g.features=List.of(new Game.Section("收集玩法","从孵化开始。"));
        g.benefits=List.of(new Game.Section("首充奖励","需首充后领取。"));
        g.faqs=List.of(new Game.Faq("能免费领取吗？","首充奖励需要充值。"));
        g.videos=List.of(new Game.Video("宣传视频","https://cdn.example/video.mp4","/media/hero.jpg"));
        g.published=published;return games.save(g);
    }
    @Test void publishedPageRendersWholeContentAndCustomMetadataWithoutJavascript() throws Exception {
        Game g=add(true);g.seoTitle="自定义搜索标题";g.seoDescription="自定义搜索摘要";games.save(g);
        mvc.perform(get("/games/dragon/")).andExpect(status().isOk())
            .andExpect(content().string(org.hamcrest.Matchers.containsString("这是服务端直接生成的完整游戏正文。")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("<h1 id=\"game-title\">恐龙游戏</h1>")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("<title>自定义搜索标题</title>")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("rel=\"canonical\" href=\"https://games.example/games/dragon/\"")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("name=\"description\" content=\"自定义搜索摘要\"")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("name=\"robots\" content=\"index,follow,max-image-preview:large\"")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("alt=\"恐龙进化画面\"")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("<video id=\"game-video\" controls playsinline preload=\"none\">")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("<summary>能免费领取吗？</summary>")));
        mvc.perform(get("/games/dragon")).andExpect(status().isMovedPermanently()).andExpect(redirectedUrl("/games/dragon/"));
        mvc.perform(get("/site/site.css")).andExpect(status().isOk());
    }
    @Test void draftAndPreviewCannotLeakIntoPublicPagesOrSitemap() throws Exception {
        add(false);
        mvc.perform(get("/games/dragon/")).andExpect(status().isNotFound());
        mvc.perform(get("/games/dragon")).andExpect(status().isNotFound());
        mvc.perform(get("/")).andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("恐龙游戏"))));
        mvc.perform(get("/sitemap.xml")).andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("dragon"))));
        mvc.perform(get("/admin/preview/14545")).andExpect(status().is3xxRedirection());
        mvc.perform(get("/admin/preview/14545").with(user("admin")))
            .andExpect(status().isOk()).andExpect(header().string("X-Robots-Tag", "noindex, follow"))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("name=\"robots\" content=\"noindex,follow\"")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("<h1 id=\"game-title\">恐龙游戏</h1>")));
    }
    @Test void unpublishingAndNoindexRemoveGameFromSitemapImmediately() throws Exception {
        Game g=add(true);
        mvc.perform(get("/sitemap.xml")).andExpect(content().string(org.hamcrest.Matchers.containsString("https://games.example/games/dragon/")));
        g.noindex=true;g=games.save(g);
        mvc.perform(get("/games/dragon/")).andExpect(content().string(org.hamcrest.Matchers.containsString("name=\"robots\" content=\"noindex,follow\"")));
        mvc.perform(get("/sitemap.xml")).andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("/games/dragon/"))));
        g.published=false;games.save(g);
        mvc.perform(get("/games/dragon/")).andExpect(status().isNotFound());
    }
    @Test void searchWorksAndNoDomainMeansNoIndexingOrFabricatedCanonical() throws Exception {
        add(true);
        mvc.perform(get("/").param("q","恐龙")).andExpect(status().isOk())
            .andExpect(content().string(org.hamcrest.Matchers.containsString("/games/dragon/")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("name=\"robots\" content=\"noindex,follow\"")));
        mvc.perform(get("/").param("q","不存在")).andExpect(content().string(org.hamcrest.Matchers.containsString("暂时没有找到这款游戏")));
        games.saveSettings(new SiteSettings());
        mvc.perform(get("/robots.txt")).andExpect(content().string("User-agent: *\nDisallow: /\n"));
        mvc.perform(get("/games/dragon/")).andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("rel=\"canonical\""))))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("name=\"robots\" content=\"noindex,follow\"")));
    }
    @Test void editorCopyIsEscapedAndStructuredDataCannotCloseScriptTag() throws Exception {
        Game g=add(true);g.summary="</script><script>alert(1)</script>";g.name="<img src=x onerror=alert(2)>";games.save(g);
        String html=mvc.perform(get("/games/dragon/")).andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        assertThat(html).doesNotContain("<script>alert(1)", "<img src=x onerror=");
        assertThat(html).contains("\\u003c/script\\u003e");
    }
}
