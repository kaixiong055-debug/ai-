package com.youxuan.cms;
import org.springframework.stereotype.Service;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ApplicationArguments;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.*;
@Service @Order(0)
public class CatalogService implements ApplicationRunner {
 private final JdbcTemplate db;private final ObjectMapper json;
 public CatalogService(JdbcTemplate db,ObjectMapper json){this.db=db;this.json=json;}
 public record Page(List<Game> items,long total,int page,int size,int pages){}
 public void run(ApplicationArguments args){
  while(true){var rows=db.query("SELECT payload FROM cms_games WHERE catalog_ready=FALSE LIMIT 100",(rs,n)->decode(rs.getString(1)));if(rows.isEmpty())break;for(Game g:rows)index(db,g);}
 }
 static void index(JdbcTemplate db,Game g){db.update("UPDATE cms_games SET name=?,category=?,search_text=?,excluded=?,recommendation_rank=?,catalog_ready=TRUE WHERE id=?",g.name,g.category,(g.name+" "+g.summary+" "+g.category+" "+g.id).toLowerCase(Locale.ROOT),g.noindex,g.recommendationRank,g.id);}
 public Page page(String q,String status,String category,String sort,int page,int size){
  size=Math.max(1,Math.min(100,size));q=q==null?"":q.trim();category=category==null?"":category.trim();
  String where=" WHERE 1=1";List<Object> params=new ArrayList<>();
  if("published".equals(status)||"draft".equals(status)){where+=" AND published=?";params.add("published".equals(status));}
  if(!category.isBlank()){where+=" AND category=?";params.add(category);}
  if(!q.isBlank()){where+=" AND search_text LIKE ? ESCAPE '!'";params.add("%"+q.toLowerCase(Locale.ROOT).replace("!","!!").replace("%","!%").replace("_","!_")+"%");}
  long total=db.queryForObject("SELECT COUNT(*) FROM cms_games"+where,Long.class,params.toArray());int pages=(int)Math.max(1,(total+size-1)/size);page=Math.max(1,Math.min(pages,page));
  String order="name".equals(sort)?"name ASC,id ASC":"recommended".equals(sort)?"recommendation_rank DESC,updated_at DESC,id ASC":"updated_at DESC,id ASC";
  params.add(size);params.add((long)(page-1)*size);
  var items=db.query("SELECT payload FROM cms_games"+where+" ORDER BY "+order+" LIMIT ? OFFSET ?",(rs,n)->decode(rs.getString(1)),params.toArray());return new Page(items,total,page,size,pages);
 }
 public Game featured(){return db.query("SELECT payload FROM cms_games WHERE published=TRUE AND recommendation_rank>0 ORDER BY recommendation_rank DESC,updated_at DESC,id ASC LIMIT 1",(rs,n)->decode(rs.getString(1))).stream().findFirst().orElse(null);}
 public List<String> categories(boolean publishedOnly){return db.queryForList("SELECT DISTINCT category FROM cms_games WHERE category<>''"+(publishedOnly?" AND published=TRUE":"")+" ORDER BY category",String.class);}
 public List<Map<String,Object>> sitemap(){return db.queryForList("SELECT slug,updated_at FROM cms_games WHERE published=TRUE AND excluded=FALSE ORDER BY id");}
 private Game decode(String payload){try{return json.readValue(payload,Game.class);}catch(Exception e){throw new IllegalStateException("游戏数据读取失败",e);}}
}
