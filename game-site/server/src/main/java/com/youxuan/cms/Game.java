package com.youxuan.cms;

import java.util.ArrayList;
import java.util.List;

/** Editable public content only. Channel account data never belongs in this DTO. */
public class Game {
 public String id="", slug="", name="", subtitle="", summary="", description="", category="", platform="Android", version="";
 public String iconUrl="", heroUrl="", downloadUrl="", introUrl="", seoTitle="", seoDescription="", seoKeywords="", ogImage="";
 public boolean noindex=false, published=false;
 public List<String> tags=new ArrayList<>();
 public List<Picture> screenshots=new ArrayList<>();
 public List<Video> videos=new ArrayList<>();
 public List<Section> features=new ArrayList<>(), benefits=new ArrayList<>();
 public List<Faq> faqs=new ArrayList<>();
 public long revision=0;
 public String createdAt="", updatedAt="";
 public record Picture(String url,String alt) {}
 public record Video(String title,String url,String poster) {}
 public record Section(String title,String text) {}
 public record Faq(String question,String answer) {}
}
