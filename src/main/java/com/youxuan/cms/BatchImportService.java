package com.youxuan.cms;

import com.fasterxml.jackson.databind.*;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;
import java.util.*;
import java.text.Normalizer;

@Service
public class BatchImportService {
 private final ObjectMapper mapper;private final GameService games;
 public BatchImportService(ObjectMapper mapper,GameService games){this.mapper=mapper;this.games=games;}
 public record Item(String gameId,String name,Integer fileIndex,String status,String message){}
 public List<Item> plan(byte[] data,List<String> filenames){
  if(data.length>2*1024*1024||filenames.size()>2000)throw bad("JSON 上限 2MB，每批最多 2000 个 ZIP");
  try{
   JsonNode root=mapper.readTree(data);JsonNode list=root.isArray()?root:root.path("result").path("data");if(!list.isArray())list=root.path("data");if(!list.isArray())list=mapper.createArrayNode().add(root);
   if(list.size()>2000)throw bad("每批最多 2000 款游戏");
   List<Item> result=new ArrayList<>();Set<String> ids=new HashSet<>();
   for(JsonNode game:list){String id=game.path("game_id").asText(game.path("id").asText("")),name=game.path("name").asText("");
    if(!id.matches("[A-Za-z0-9_-]{1,64}")||name.isBlank()){result.add(new Item(id,name,null,"error","缺少合法游戏 ID 或名称"));continue;}
    if(!ids.add(id)){result.add(new Item(id,name,null,"error","JSON 中游戏 ID 重复"));continue;}
    if(games.find(id).isPresent()){result.add(new Item(id,name,null,"skipped","已入库，跳过且不覆盖"));continue;}
    List<Integer> matches=new ArrayList<>();for(int i=0;i<filenames.size();i++){String file=filenames.get(i);if(file==null||file.length()>1024)throw bad("文件名无效");String base=file.replace('\\','/');base=base.substring(base.lastIndexOf('/')+1);if(!base.toLowerCase(Locale.ROOT).endsWith(".zip"))continue;base=base.substring(0,base.length()-4);
     if(base.equals(id)||(normalize(base).equals(normalize(name))||normalize(base).replaceFirst("(?:游戏素材|素材包|素材)$", "").equals(normalize(name))))matches.add(i);
    }
    if(matches.size()==1)result.add(new Item(id,name,matches.get(0),"ready","待导入"));else result.add(new Item(id,name,null,"error",matches.isEmpty()?"未找到匹配 ZIP，请使用游戏名称或 ID 命名":"匹配到多个 ZIP，请移除重复素材包"));
   }
   Map<Integer,Long> uses=new HashMap<>();for(Item row:result)if(row.fileIndex()!=null)uses.merge(row.fileIndex(),1L,Long::sum);
   for(int i=0;i<result.size();i++){Item row=result.get(i);if(row.fileIndex()!=null&&uses.get(row.fileIndex())>1)result.set(i,new Item(row.gameId(),row.name(),null,"error","同一 ZIP 匹配多个游戏，请改用游戏 ID 命名"));}
   Set<Integer> used=new HashSet<>();for(Item row:result)if(row.fileIndex()!=null)used.add(row.fileIndex());
   // Extra files are reported; an existing game's package need not be uploaded.
   for(int i=0;i<filenames.size();i++)if(!used.contains(i))result.add(new Item("",filenames.get(i),i,"unused","素材包未用于本次导入（已入库、未匹配或存在歧义）"));
   return result;
  }catch(ResponseStatusException e){throw e;}catch(Exception e){throw bad("无法读取 JSON，请检查文件格式");}
 }
 private static String normalize(String value){return Normalizer.normalize(value,Normalizer.Form.NFKC).replaceAll("[《》〈〉【】\\[\\]\\s]","").toLowerCase(Locale.ROOT);}
 private static ResponseStatusException bad(String message){return new ResponseStatusException(HttpStatus.BAD_REQUEST,message);}
}
