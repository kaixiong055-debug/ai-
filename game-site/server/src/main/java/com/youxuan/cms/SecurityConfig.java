package com.youxuan.cms;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.authentication.DelegatingAuthenticationEntryPoint;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.RequestMatcher;
import java.util.LinkedHashMap;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.web.filter.OncePerRequestFilter;
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.ConcurrentHashMap;

@Configuration
public class SecurityConfig {
 private static final String[] PUBLIC_READ_PATHS={"/","/games/**","/assets/**","/site/**","/media/**","/robots.txt","/sitemap.xml","/favicon.ico","/error","/login","/admin/admin.css","/admin/admin.js"};
 private final LoginThrottle throttle=new LoginThrottle();
 @Bean PasswordEncoder passwordEncoder(){return new BCryptPasswordEncoder();}
 @Bean UserDetailsService users(@Value("${cms.admin.username:admin}") String username,@Value("${cms.admin.password:}") String password,PasswordEncoder encoder){
  if("CHANGE_ME_BEFORE_STARTING".equalsIgnoreCase(password))throw new IllegalStateException("请替换环境配置中的 GAME_ADMIN_PASSWORD 示例密码后启动");
  if(password.isBlank()||password.length()<12||password.getBytes(java.nio.charset.StandardCharsets.UTF_8).length>72)throw new IllegalStateException("请设置 GAME_ADMIN_PASSWORD，至少 12 个字符且不超过 72 个 UTF-8 字节；没有默认管理员密码");
  if(username.isBlank()||username.length()>100)throw new IllegalStateException("GAME_ADMIN_USERNAME 必须为 1 至 100 个字符");
  return new InMemoryUserDetailsManager(User.withUsername(username).password(encoder.encode(password)).roles("ADMIN").build());
 }
 @Bean SecurityFilterChain security(HttpSecurity http)throws Exception{
  http.authorizeHttpRequests(a->a.requestMatchers(HttpMethod.GET,PUBLIC_READ_PATHS).permitAll().requestMatchers(HttpMethod.HEAD,PUBLIC_READ_PATHS).permitAll().requestMatchers("/login").permitAll().anyRequest().authenticated());
  http.formLogin(f->f.loginPage("/login").successHandler((request,response,auth)->{throttle.reset(request.getRemoteAddr());response.sendRedirect(request.getContextPath()+"/admin");}).failureHandler((request,response,error)->{throttle.failed(request.getRemoteAddr());response.sendRedirect(request.getContextPath()+"/login?error");}));
  http.logout(l->l.logoutSuccessUrl("/login?logout").invalidateHttpSession(true).deleteCookies("JSESSIONID"));
  LinkedHashMap<RequestMatcher,AuthenticationEntryPoint> entries=new LinkedHashMap<>();
  entries.put(new AntPathRequestMatcher("/api/**"),(request,response,error)->{response.setStatus(401);response.setContentType("application/json;charset=UTF-8");response.getWriter().write("{\"message\":\"登录已过期，请重新登录\"}");});
  DelegatingAuthenticationEntryPoint entryPoint=new DelegatingAuthenticationEntryPoint(entries);
  entryPoint.setDefaultEntryPoint(new LoginUrlAuthenticationEntryPoint("/login"));
  http.exceptionHandling(e->e.authenticationEntryPoint(entryPoint).accessDeniedHandler((request,response,error)->{response.setStatus(403);response.setContentType("application/json;charset=UTF-8");response.getWriter().write("{\"message\":\"请求校验失败，请刷新页面后重试\"}");}));
  http.headers(h->h.contentSecurityPolicy(c->c.policyDirectives("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https: data:; media-src 'self' https:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")));
  http.addFilterBefore(new OncePerRequestFilter(){@Override protected void doFilterInternal(HttpServletRequest request,HttpServletResponse response,FilterChain chain)throws ServletException,IOException{
   String uri=request.getRequestURI();if(uri.startsWith("/admin")||uri.startsWith("/api/admin")||uri.equals("/login")){response.setHeader("X-Robots-Tag","noindex, nofollow");response.setHeader("Cache-Control","no-store");}
   if(uri.equals("/login")&&request.getMethod().equals("POST")&&throttle.blocked(request.getRemoteAddr())){response.setStatus(429);response.setHeader("Retry-After","900");response.setContentType("text/plain;charset=UTF-8");response.getWriter().write("登录尝试过多，请 15 分钟后重试");return;}chain.doFilter(request,response);
  }},UsernamePasswordAuthenticationFilter.class);
  return http.build();
 }
 static final class LoginThrottle {
  private record Attempts(int count,long started){}
  private final ConcurrentHashMap<String,Attempts> failures=new ConcurrentHashMap<>();
  private static final long WINDOW=Duration.ofMinutes(15).toMillis();
  boolean blocked(String ip){Attempts a=failures.get(ip);if(a==null)return false;if(System.currentTimeMillis()-a.started>WINDOW){failures.remove(ip,a);return false;}return a.count>=12;}
  void failed(String ip){long now=System.currentTimeMillis();if(failures.size()>5000){failures.entrySet().removeIf(e->now-e.getValue().started>WINDOW);if(failures.size()>5000)return;}failures.compute(ip,(key,a)->a==null||now-a.started>WINDOW?new Attempts(1,now):new Attempts(a.count+1,a.started));}
  void reset(String ip){failures.remove(ip);}
 }
}
