package com.youxuan.cms;

import java.net.URI;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** URL allowlist for rendered attributes. This class never fetches remote URLs. */
public final class UrlPolicy {
 private UrlPolicy(){}
 public static String external(String input){
  String value=input==null?"":input.trim();if(value.isEmpty())return "";
  if(value.length()>2048||value.chars().anyMatch(c->c<=32||c==127)||value.contains("\\"))throw invalid();
  try{
   URI uri=URI.create(value);String host=uri.getHost();
   if(!"https".equalsIgnoreCase(uri.getScheme())||host==null||host.isBlank()||uri.getUserInfo()!=null||uri.getRawAuthority().contains("@"))throw invalid();
   String h=host.toLowerCase();
   if(h.equals("localhost")||h.endsWith(".localhost")||h.endsWith(".local")||h.equals("127.0.0.1")||h.equals("[::1]")||h.equals("0.0.0.0"))throw invalid();
   return value;
  }catch(IllegalArgumentException e){throw invalid();}
 }
 public static String media(String input){String value=input==null?"":input.trim();if(value.startsWith("/media/")&&value.matches("/media/[A-Za-z0-9_-]+\\.(jpg|jpeg|png|webp|gif)"))return value;return external(value);}
 public static String site(String input){String value=external(input);if(value.isEmpty())return value;URI uri=URI.create(value);if(uri.getRawQuery()!=null||uri.getRawFragment()!=null||!(uri.getRawPath().isEmpty()||uri.getRawPath().equals("/")))throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"网站域名只能填写 HTTPS 根域名，例如 https://game.example.com");return value.replaceAll("/+$","");}
 private static ResponseStatusException invalid(){return new ResponseStatusException(HttpStatus.BAD_REQUEST,"链接必须是有效的 HTTPS 地址；图片也可使用已上传的 /media/ 文件地址");}
}
