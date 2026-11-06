package com.youxuan.cms;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.server.ResponseStatusException;
import java.util.UUID;
import static org.assertj.core.api.Assertions.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties={"spring.datasource.url=jdbc:h2:mem:core;DB_CLOSE_DELAY=-1", "cms.admin.password=test-password-long-enough", "cms.demo.enabled=false"})
@AutoConfigureMockMvc
class CoreTests {
 @Autowired GameService service;
 @Autowired MockMvc mvc;
 @Autowired ObjectMapper mapper;
 Game sample(){Game g=new Game();g.name="测试恐龙";g.slug="test-"+UUID.randomUUID();g.summary="阵容养成";g.description="恐龙培养与冒险";g.iconUrl="https://images.example/icon.jpg";g.heroUrl="https://images.example/hero.jpg";g.downloadUrl="https://m.3387.com/s/abc?d=1";return g;}
 @Test void draftPublishesAndUnpublishesWithoutLosingSlugLock(){Game g=service.save(sample());assertThat(service.publishedBySlug(g.slug)).isEmpty();g.published=true;g=service.save(g);assertThat(service.publishedBySlug(g.slug)).isPresent();g.published=false;g=service.save(g);assertThat(service.publishedBySlug(g.slug)).isEmpty();g.slug="changed-"+UUID.randomUUID();Game change=g;assertThatThrownBy(()->service.save(change)).isInstanceOf(ResponseStatusException.class).hasMessageContaining("URL");}
 @Test void staleRevisionAndDuplicateSlugCannotOverwrite(){Game original=service.save(sample());Game stale=service.find(original.id).orElseThrow();original.name="新标题";service.save(original);stale.name="旧标题";assertThatThrownBy(()->service.save(stale)).isInstanceOf(ResponseStatusException.class).hasMessageContaining("更新");assertThat(service.find(original.id).orElseThrow().name).isEqualTo("新标题");Game duplicate=sample();duplicate.slug=original.slug;assertThatThrownBy(()->service.save(duplicate)).isInstanceOf(ResponseStatusException.class);}
 @Test void publishRejectsIncompleteAndUnsafeLinks(){Game g=new Game();g.name="未完成";g.published=true;assertThatThrownBy(()->service.save(g)).isInstanceOf(ResponseStatusException.class);Game invalid=sample();invalid.downloadUrl="javascript:alert(1)";assertThatThrownBy(()->service.save(invalid)).isInstanceOf(ResponseStatusException.class);assertThatThrownBy(()->UrlPolicy.media("/media/../secret")).isInstanceOf(ResponseStatusException.class);assertThatThrownBy(()->UrlPolicy.external("https://user:secret@example.com/a")).isInstanceOf(ResponseStatusException.class);}
 @Test void deleteRequiresCurrentRevision(){Game g=service.save(sample());assertThatThrownBy(()->service.delete(g.id,g.revision-1)).isInstanceOf(ResponseStatusException.class);service.delete(g.id,g.revision);assertThat(service.find(g.id)).isEmpty();}
 @Test void settingsPersistAndRejectInvalidCanonicalDomain(){SiteSettings s=new SiteSettings();s.siteName="我的游戏站";s.siteUrl="https://games.example";s.allowIndexing=true;service.saveSettings(s);assertThat(service.settings().siteName).isEqualTo(s.siteName);s.siteUrl="https://games.example/path";assertThatThrownBy(()->service.saveSettings(s)).isInstanceOf(ResponseStatusException.class);}
 @Test void unauthenticatedApiIs401AndAdminRequiresLogin() throws Exception {mvc.perform(get("/api/admin/games")).andExpect(status().isUnauthorized());mvc.perform(get("/admin")).andExpect(status().is3xxRedirection());mvc.perform(post("/api/admin/games").contentType(MediaType.APPLICATION_JSON).content("{}" )).andExpect(status().isForbidden());}
 @Test @WithMockUser void apiRequiresCsrfAndReturnsCreatedRecord() throws Exception {mvc.perform(post("/api/admin/games").contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(sample()))).andExpect(status().isForbidden());mvc.perform(post("/api/admin/games").with(csrf()).contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(sample()))).andExpect(status().isCreated()).andExpect(jsonPath("revision").value(1));mvc.perform(get("/api/admin/session")).andExpect(status().isOk()).andExpect(jsonPath("token").isNotEmpty()).andExpect(header().string("X-Robots-Tag","noindex, nofollow"));}
 @Test @WithMockUser void putCannotCreateOrChangeIdentity() throws Exception {Game g=service.save(sample());g.id="some-other-id";mvc.perform(put("/api/admin/games/"+UUID.randomUUID()).with(csrf()).contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsString(g))).andExpect(status().is4xxClientError());}
 @Test void throttleBlocksRepeatedFailuresAndSuccessResets(){SecurityConfig.LoginThrottle limiter=new SecurityConfig.LoginThrottle();for(int i=0;i<12;i++)limiter.failed("192.0.2.1");assertThat(limiter.blocked("192.0.2.1")).isTrue();assertThat(limiter.blocked("192.0.2.2")).isFalse();limiter.reset("192.0.2.1");assertThat(limiter.blocked("192.0.2.1")).isFalse();}
 @Test void examplePasswordIsRejected(){SecurityConfig config=new SecurityConfig();assertThatThrownBy(()->config.users("admin","CHANGE_ME_BEFORE_STARTING",config.passwordEncoder())).isInstanceOf(IllegalStateException.class).hasMessageContaining("示例密码");}
 @Test void loginAssetsArePublicButAdminRemainsProtected() throws Exception {mvc.perform(get("/admin/admin.css")).andExpect(status().isOk());mvc.perform(get("/admin/admin.js")).andExpect(status().isOk());mvc.perform(get("/admin").accept(MediaType.ALL)).andExpect(status().is3xxRedirection()).andExpect(redirectedUrl("http://localhost/login"));mvc.perform(get("/api/admin/games").accept(MediaType.TEXT_HTML)).andExpect(status().isUnauthorized());}
 @Test void headRequestsReadPublicPagesWithoutLogin() throws Exception {Game g=sample();g.published=true;g=service.save(g);mvc.perform(head("/games/"+g.slug+"/")).andExpect(status().isOk()).andExpect(header().doesNotExist("Location"));mvc.perform(head("/site/site.css")).andExpect(status().isOk());mvc.perform(head("/sitemap.xml")).andExpect(status().isOk());mvc.perform(head("/robots.txt")).andExpect(status().isOk());mvc.perform(head("/media/missing.jpg")).andExpect(status().isNotFound());mvc.perform(head("/api/admin/games")).andExpect(status().isUnauthorized());mvc.perform(head("/admin")).andExpect(status().is3xxRedirection());}
 @Test void loginUsesConfiguredCredentials() throws Exception {mvc.perform(post("/login").with(csrf()).param("username","admin").param("password","wrong-password")).andExpect(redirectedUrl("/login?error"));mvc.perform(post("/login").with(csrf()).param("username","admin").param("password","test-password-long-enough")).andExpect(redirectedUrl("/admin"));}
}
