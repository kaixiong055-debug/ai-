package com.youxuan.cms;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
@SpringBootTest(properties={"spring.datasource.url=jdbc:h2:mem:catalog;DB_CLOSE_DELAY=-1","cms.admin.password=CatalogTestOnly-2026","cms.demo.enabled=false","cms.data-dir=${java.io.tmpdir}/cms-catalog-test"})
@AutoConfigureMockMvc
class CatalogTest {
 @Autowired CatalogService catalog;@Autowired GameService games;@Autowired JdbcTemplate db;@Autowired ObjectMapper json;@Autowired MockMvc mvc;
 @BeforeEach void reset(){db.update("DELETE FROM cms_games");db.update("DELETE FROM cms_settings");SiteSettings s=new SiteSettings();s.siteUrl="https://games.example";s.allowIndexing=true;games.saveSettings(s);}
 Game add(int n,boolean published){Game g=new Game();g.id="g"+n;g.slug="game-"+n;g.name=String.format("游戏%04d",n);g.category=n%2==0?"卡牌":"冒险";g.summary="玩法介绍";g.description="真实玩法介绍";g.iconUrl="/media/icon.jpg";g.heroUrl="/media/hero.jpg";g.downloadUrl="https://example.com/download";g.published=published;return games.save(g);}
 @Test void databasePaginationFiltersAndClamps(){for(int i=0;i<55;i++)add(i,i<50);var first=catalog.page("","published","","name",1,20);var second=catalog.page("","published","","name",2,20);assertThat(first.total()).isEqualTo(50);assertThat(first.items()).hasSize(20);assertThat(second.items()).extracting(g->g.id).doesNotContainAnyElementsOf(first.items().stream().map(g->g.id).toList());assertThat(catalog.page("","draft","","latest",99,20).items()).hasSize(5);assertThat(catalog.page("","published","卡牌","name",1,20).total()).isEqualTo(25);assertThat(catalog.page("游戏0001","","","name",1,20).total()).isEqualTo(1);assertThat(catalog.page("%","","","name",1,20).total()).isZero();assertThat(catalog.page("_","","","name",1,20).total()).isZero();assertThat(catalog.page("","","","name",-1,10000).size()).isEqualTo(100);}
 @Test void pagesAreRenderedWithoutJavascriptAndHaveOwnCanonical()throws Exception{for(int i=0;i<40;i++)add(i,true);add(99,false);String html=mvc.perform(get("/").param("page","2")).andExpect(status().isOk()).andReturn().getResponse().getContentAsString();assertThat(html.split("class=\"home-card\"",-1).length-1).isEqualTo(18);assertThat(html).contains("https://games.example/?page=2","rel=\"next\"","rel=\"prev\"").doesNotContain("游戏0099");mvc.perform(get("/").param("category","卡牌")).andExpect(status().isOk()).andExpect(content().string(org.hamcrest.Matchers.containsString("noindex,follow")));mvc.perform(get("/api/admin/games/page").with(user("admin")).param("size","20")).andExpect(status().isOk()).andExpect(jsonPath("$.total").value(41)).andExpect(jsonPath("$.items.length()").value(20));}
 @Test void oldRecordsBackfillAndEditsUpdateIndex()throws Exception{Game g=add(1,true);db.update("UPDATE cms_games SET catalog_ready=FALSE,search_text='',category='',excluded=TRUE");catalog.run(null);assertThat(catalog.page("游戏0001","published","冒险","latest",1,20).total()).isEqualTo(1);assertThat(catalog.sitemap()).hasSize(1);g.category="策略";g.noindex=true;games.save(g);assertThat(catalog.page("","published","冒险","latest",1,20).total()).isZero();assertThat(catalog.sitemap()).isEmpty();}
 @Test void thousandRecordsOnlyReturnRequestedPage()throws Exception{String payload=json.writeValueAsString(new Game());for(int i=0;i<1000;i++)db.update("INSERT INTO cms_games(id,slug,payload,published,revision,updated_at,catalog_ready)VALUES(?,?,?,TRUE,1,?,TRUE)","bulk"+i,"bulk-"+i,payload,"2026-01-01T00:00:00Z");var page=catalog.page("","published","","latest",30,20);assertThat(page.total()).isEqualTo(1000);assertThat(page.pages()).isEqualTo(50);assertThat(page.items()).hasSize(20);}
 @Test void recommendationsLeadHomepageAndRespectPublication()throws Exception{
  Game first=add(1,true);add(2,true);first.recommendationRank=100;first=games.save(first);
  assertThat(catalog.page("","published","","recommended",1,18).items().get(0).id).isEqualTo(first.id);
  Game other=add(3,true);other.recommendationRank=200;other=games.save(other);
  assertThat(catalog.featured().id).isEqualTo(other.id);
  String html=mvc.perform(get("/")).andExpect(status().isOk()).andReturn().getResponse().getContentAsString();assertThat(html).contains("class=\"featured-game\" href=\"/games/game-3/\"");
  other.published=false;games.save(other);assertThat(catalog.featured().id).isEqualTo(first.id);
  first.recommendationRank=0;games.save(first);assertThat(catalog.featured()).isNull();
 }
 @Test void invalidRecommendationIsRejected(){Game g=add(1,false);g.recommendationRank=-1;org.assertj.core.api.Assertions.assertThatThrownBy(()->games.save(g)).isInstanceOf(org.springframework.web.server.ResponseStatusException.class);}
 @Test void sitemapIsValidXmlAndAutomaticallyTracksLifecycle()throws Exception{
  Game g=add(1,false);String before=mvc.perform(get("/sitemap.xml")).andReturn().getResponse().getContentAsString();assertThat(before).doesNotContain("game-1");
  g.published=true;g=games.save(g);String xml=mvc.perform(get("/sitemap.xml")).andExpect(header().string("Cache-Control","no-store")).andReturn().getResponse().getContentAsString();
  var factory=javax.xml.parsers.DocumentBuilderFactory.newInstance();factory.setNamespaceAware(true);var doc=factory.newDocumentBuilder().parse(new java.io.ByteArrayInputStream(xml.getBytes(java.nio.charset.StandardCharsets.UTF_8)));
  assertThat(doc.getElementsByTagNameNS("http://www.sitemaps.org/schemas/sitemap/0.9","url").getLength()).isEqualTo(2);assertThat(xml).contains("/games/game-1/","xml-stylesheet").doesNotContain("...");
  g.category="新分类";g=games.save(g);assertThat(catalog.categories(true)).contains("新分类");
  g.published=false;games.save(g);assertThat(mvc.perform(get("/sitemap.xml")).andReturn().getResponse().getContentAsString()).doesNotContain("/games/game-1/");
 }
}
