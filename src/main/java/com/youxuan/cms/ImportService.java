package com.youxuan.cms;

import com.fasterxml.jackson.databind.*;
import org.springframework.stereotype.Service;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.io.*;
import java.nio.charset.*;
import java.util.*;
import java.util.zip.*;

@Service
public class ImportService {
 private final GameService games;private final MediaService media;private final ObjectMapper mapper;
 public ImportService(GameService games,MediaService media,ObjectMapper mapper){this.games=games;this.media=media;this.mapper=mapper;}
 public synchronized Game importGame(byte[] json,InputStream archive,String gameId){
  if(json.length>2*1024*1024)throw bad("JSON 文件不能超过 2MB");
  try{
   JsonNode source=select(mapper.readTree(json),gameId);
   Game game=new Game();game.id=text(source,"game_id",text(source,"id",""));
   if(!game.id.matches("[a-zA-Z0-9_-]{1,64}"))throw bad("JSON 中缺少合法商品游戏 ID");
   if(games.find(game.id).isPresent())throw new ResponseStatusException(HttpStatus.CONFLICT,"该游戏已存在，请在游戏管理中编辑，导入不会覆盖已有资料");
   game.slug=game.id.toLowerCase(Locale.ROOT).replace('_','-');game.name=text(source,"name","");
   if(game.name.isBlank())throw bad("JSON 中缺少游戏名称");
   game.downloadUrl=UrlPolicy.external(text(source,"pkg_url",source.path("links").path("download").asText("")));
   game.introUrl=UrlPolicy.external(text(source,"activity_url",source.path("links").path("intro").asText("")));
   game.version=source.path("android").path("version").asText(source.path("version").path("android").asText(""));
   game.platform="Android";game.published=false;
   List<Asset> assets=readArchive(archive);
   Set<String> gallery=new HashSet<>();
   for(Asset a:assets){
    String lower=a.name.toLowerCase(Locale.ROOT);
    if(lower.endsWith(".txt")){
     String content=decode(a.bytes).strip();
     if(lower.contains("一句话"))game.summary=content;
     else if(lower.contains("简介"))game.description=content;
     else if(lower.contains("福利")&&!content.isBlank())game.benefits.add(new Game.Section("游戏福利",content));
    } else if(lower.matches(".*\\.(jpg|jpeg|png|gif)$")){
     String url=media.store(a.bytes,a.name,game.id).url();
     if(lower.contains("icon")||lower.contains("图标")){if(game.iconUrl.isBlank())game.iconUrl=url;}
     else if(lower.contains("banner")||lower.contains("横幅")){if(game.heroUrl.isBlank())game.heroUrl=url;}
     else if(lower.contains("截图")||lower.contains("screenshot")){if(gallery.add(url))game.screenshots.add(new Game.Picture(url,game.name+"游戏画面 "+(gallery.size())));}
    }
   }
   if(game.summary.isBlank())game.summary=game.description.length()>150?game.description.substring(0,150):game.description;
   if(game.description.isBlank())game.description=source.path("intro").asText("");
   // Only the known, public game fields are copied. Commission, signed ZIP and channel data stay private.
   game.videos.addAll(videoLinks(source.path("video_list"),"游戏宣传视频"));
   game.videos.addAll(videoLinks(source.path("probation_video_list"),"游戏试玩视频"));
   return games.save(game);
  }catch(ResponseStatusException e){throw e;}catch(IOException|IllegalArgumentException e){throw bad("无法读取 JSON 或 ZIP，请确认文件格式和中文文件名编码");}
 }
 private JsonNode select(JsonNode root,String id){
  JsonNode list=root.path("result").path("data");if(list.isMissingNode())list=root.path("data");if(root.isArray())list=root;
  if(!list.isArray()){String actual=text(root,"game_id",text(root,"id",""));if(id!=null&&!id.isBlank()&&!id.equals(actual))throw bad("所选游戏 ID 与 JSON 不匹配");return root;}
  if((id==null||id.isBlank())&&list.size()==1)return list.get(0);
  for(JsonNode g:list)if(text(g,"game_id",text(g,"id","")).equals(id))return g;
  throw bad("请填写 JSON 列表中的游戏 ID，未找到对应游戏");
 }
 private static List<Game.Video> videoLinks(JsonNode list,String title){
  List<Game.Video> result=new ArrayList<>();if(!list.isArray())return result;
  for(JsonNode node:list){String url=node.isTextual()?node.asText():node.path("url").asText("");
   if(!url.isBlank())try{result.add(new Game.Video(title,UrlPolicy.external(url),""));}catch(ResponseStatusException ignored){}
   if(result.size()>=4)break;
  }return result;
 }
 private record Asset(String name,byte[] bytes){}
 private List<Asset> readArchive(InputStream input)throws IOException{
  var results=new ArrayList<Asset>();long total=0;int entries=0;byte[] buffer=new byte[8192];
  try(var zip=new ZipInputStream(input,Charset.forName("GB18030"))){
   ZipEntry entry;while((entry=zip.getNextEntry())!=null){
    if(++entries>200)throw bad("ZIP 条目超过 200 个");
    String name=entry.getName().replace('\\','/');
    if(name.startsWith("/")||name.contains(":")||Arrays.asList(name.split("/")).contains("..")||name.indexOf('\0')>=0)throw bad("ZIP 包含不安全路径");
    String lower=name.toLowerCase(Locale.ROOT);
    boolean text=lower.endsWith(".txt"),image=lower.matches(".*\\.(jpg|jpeg|png|gif)$");
    boolean keep=!entry.isDirectory()&&(text||image);
    ByteArrayOutputStream out=keep?new ByteArrayOutputStream():null;long size=0;int n;
    while((n=zip.read(buffer))!=-1){size+=n;total+=n;
     if(total>128L*1024*1024)throw bad("ZIP 解压内容超过 128MB");
     if(keep&&size>(text?256*1024:MediaService.MAX_IMAGE_BYTES))throw bad("ZIP 中图片或文本文件过大");
     if(keep)out.write(buffer,0,n);
    }
    if(keep)results.add(new Asset(name,out.toByteArray()));zip.closeEntry();
   }
  }
  if(entries==0)throw bad("ZIP 为空或格式无效");
  results.sort(Comparator.comparing(Asset::name));return results;
 }
 private static String decode(byte[] bytes)throws CharacterCodingException{
  try{return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).decode(java.nio.ByteBuffer.wrap(bytes)).toString().replace("\uFEFF","");}
  catch(CharacterCodingException e){return Charset.forName("GB18030").newDecoder().decode(java.nio.ByteBuffer.wrap(bytes)).toString();}
 }
 private static String text(JsonNode n,String key,String fallback){return n.path(key).isValueNode()?n.path(key).asText(fallback):fallback;}
 private static ResponseStatusException bad(String s){return new ResponseStatusException(HttpStatus.BAD_REQUEST,s);}
}
