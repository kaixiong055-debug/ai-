package com.youxuan.cms;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;
@Component
@ConditionalOnProperty(name="cms.demo.enabled",havingValue="true")
public class DemoSeed implements ApplicationRunner{
 private final GameService games;private final MediaService media;private final ObjectMapper json;
 public DemoSeed(GameService games,MediaService media,ObjectMapper json){this.games=games;this.media=media;this.json=json;}
 public void run(ApplicationArguments args)throws Exception{
  if(games.find("14545").isPresent())return;
  Game game;try(var input=new ClassPathResource("sample/game.json").getInputStream()){game=json.readValue(input,Game.class);}
  game.iconUrl=picture("icon.jpg");game.heroUrl=picture("hero.jpg");
  String[] labels={"布阵与战斗","基因抽取与强化","恐龙进化","恐龙继承","孵化与收集"};
  for(int i=0;i<5;i++)game.screenshots.add(new Game.Picture(picture("shot-0"+(i+1)+".jpg"),labels[i]));
  game.published=false;games.save(game);
 }
 private String picture(String name)throws Exception{try(var in=new ClassPathResource("sample/"+name).getInputStream()){return media.store(in.readAllBytes(),name).url();}}
}
