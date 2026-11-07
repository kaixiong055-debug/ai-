package com.youxuan.cms;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
@Controller
public class AdminPageController {
 @GetMapping({"/admin","/admin/"})public String admin(){return "admin";}
 @GetMapping("/login")public String login(){return "login";}
}
