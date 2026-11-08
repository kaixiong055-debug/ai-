package com.youxuan.cms;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.mock.web.MockHttpSession;
import java.util.regex.Pattern;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.*;
import static org.assertj.core.api.Assertions.*;
@SpringBootTest(properties={"spring.datasource.url=jdbc:h2:mem:loginrecovery;DB_CLOSE_DELAY=-1","cms.admin.password=test-admin-password-123","cms.demo.enabled=false"})
@AutoConfigureMockMvc
class LoginRecoveryTest {
 @Autowired MockMvc mvc;
 @Test void staleLoginReturnsFreshFormAndCanAuthenticate()throws Exception{
  mvc.perform(post("/login").param("username","admin").param("password","test-admin-password-123").param("_csrf","stale"))
   .andExpect(status().isSeeOther()).andExpect(redirectedUrl("/login?expired"));
  var form=mvc.perform(get("/login?expired")).andExpect(status().isOk()).andExpect(content().string(org.hamcrest.Matchers.containsString("登录页面已失效"))).andReturn();
  var matcher=Pattern.compile("name=\"_csrf\"[^>]*value=\"([^\"]+)\"").matcher(form.getResponse().getContentAsString());assertThat(matcher.find()).isTrue();
  var session=(MockHttpSession)form.getRequest().getSession(false);assertThat(session).isNotNull();
  mvc.perform(post("/login").session(session).param("username","admin").param("password","test-admin-password-123").param("_csrf",matcher.group(1)))
   .andExpect(status().is3xxRedirection()).andExpect(redirectedUrl("/admin"));
  mvc.perform(get("/api/admin/session").session(session)).andExpect(status().isOk());
 }
 @Test void apiCsrfStillEnforcedAndLogoutClearsOwnCookie()throws Exception{
  mvc.perform(post("/api/admin/games").with(user("admin")).contentType("application/json").content("{}")) .andExpect(status().isForbidden());
  mvc.perform(post("/logout").with(user("admin")).with(csrf())).andExpect(cookie().maxAge("GAME_CMS_SESSION",0));
 }
}
