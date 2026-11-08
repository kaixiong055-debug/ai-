package com.youxuan.cms;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ApplicationArguments;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
/** Copy first, then update the row. Legacy files remain available for old URLs and shared references. */
@Component @Order(100)
public class MediaMigration implements ApplicationRunner {
 private final GameService games;private final MediaService media;private final ObjectMapper json;
 public MediaMigration(GameService games,MediaService media,ObjectMapper json){this.games=games;this.media=media;this.json=json;}
 public void run(ApplicationArguments args)throws Exception{
  for(Game game:games.list("","")){
   String before=json.writeValueAsString(game);media.organize(game);
   if(!before.equals(json.writeValueAsString(game)))games.save(game);
  }
 }
}
