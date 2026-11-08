package com.youxuan.cms;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import javax.imageio.ImageIO;
import javax.imageio.ImageReader;
import javax.imageio.stream.ImageInputStream;
import java.io.*;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.awt.image.BufferedImage;

@Service
public class MediaService {
 public static final int MAX_IMAGE_BYTES=12*1024*1024;
 private final Path uploads;
 public record Upload(String url,String name){}
 public MediaService(@Value("${cms.data-dir:./data}") String directory){uploads=Path.of(directory).toAbsolutePath().normalize().resolve("uploads");}
 public Upload store(byte[] bytes,String name){return store(bytes,name,null);}
 public Upload store(byte[] bytes,String name,String gameId){
  if(gameId!=null&&!gameId.matches("[A-Za-z0-9_-]{1,100}"))throw bad("游戏ID格式不正确");
  if(bytes.length==0||bytes.length>MAX_IMAGE_BYTES)throw bad("图片大小须在 1 字节至 12MB 之间");
  try(ImageInputStream input=ImageIO.createImageInputStream(new ByteArrayInputStream(bytes))){
   var readers=ImageIO.getImageReaders(input);
   if(!readers.hasNext())throw bad("请上传有效的 JPG、PNG 或 GIF 图片");
   ImageReader reader=readers.next();
   try{
    String format=reader.getFormatName().toLowerCase();
    if(!java.util.Set.of("jpeg","jpg","png","gif").contains(format))throw bad("只支持 JPG、PNG 或 GIF 图片");
    reader.setInput(input,true,true);
    int width=reader.getWidth(0),height=reader.getHeight(0);
    if(width<1||height<1||width>10000||height>10000||(long)width*height>30_000_000)throw bad("图片尺寸过大（最多3000万像素）");
    BufferedImage image=reader.read(0);
    String ext=format.equals("jpeg")||format.equals("jpg")?"jpg":"png";
    var clean=new ByteArrayOutputStream();
    if(!ImageIO.write(image,ext,clean))throw bad("无法读取图片格式");
    byte[] normalized=clean.toByteArray();
    return saveBytes(normalized,ext,gameId);

   }finally{reader.dispose();}
  }catch(ResponseStatusException e){throw e;}catch(IOException e){throw bad("图片损坏或服务器存储不可用");}
 }
 private synchronized Upload saveBytes(byte[] bytes,String ext,String gameId)throws IOException {
  Path directory=gameId==null?uploads:uploads.resolve(gameId);Files.createDirectories(directory);
  String filename;
  if(gameId==null){try{filename=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes))+"."+ext;}catch(java.security.NoSuchAlgorithmException e){throw new IllegalStateException(e);}}
  else{
   long next=1;
   try(var files=Files.list(directory)){
    for(Path path:files.toList()){
     String n=path.getFileName().toString();if(!n.matches("[1-9][0-9]*\\.(jpg|png)"))continue;
     next=Math.max(next,Long.parseLong(n.substring(0,n.indexOf('.')))+1);
     if(Files.size(path)==bytes.length&&java.util.Arrays.equals(Files.readAllBytes(path),bytes))return new Upload("/media/"+gameId+"/"+n,n);
    }
   }
   filename=next+"."+ext;
  }
  Path target=directory.resolve(filename);
  if(!Files.exists(target)){
   Path temp=Files.createTempFile(directory,".upload-",".tmp");
   try{Files.write(temp,bytes);try{Files.move(temp,target,StandardCopyOption.ATOMIC_MOVE);}catch(AtomicMoveNotSupportedException e){Files.move(temp,target);}}finally{Files.deleteIfExists(temp);}
  }
  return new Upload("/media/"+(gameId==null?"":gameId+"/")+filename,filename);
 }
 public String rehome(String gameId,String url){
  if(url==null||!url.startsWith("/media/")||url.startsWith("/media/"+gameId+"/"))return url;
  if(!gameId.matches("[A-Za-z0-9_-]{1,100}"))throw bad("游戏ID格式不正确");
  Path source;try{source=file(url.substring(7));}catch(ResponseStatusException e){return url;}
  try{return saveBytes(Files.readAllBytes(source),url.endsWith(".jpg")?"jpg":"png",gameId).url();}catch(IOException e){throw bad("无法迁移游戏图片，请检查数据目录权限");}
 }
 public void organize(Game g){
  g.iconUrl=rehome(g.id,g.iconUrl);g.heroUrl=rehome(g.id,g.heroUrl);g.ogImage=rehome(g.id,g.ogImage);
  g.screenshots=g.screenshots.stream().map(p->new Game.Picture(rehome(g.id,p.url()),p.alt())).toList();
  g.videos=g.videos.stream().map(v->new Game.Video(v.title(),v.url(),rehome(g.id,v.poster()))).toList();
 }
 public Path file(String fileName){
  if(!fileName.matches("(?:[a-f0-9]{64}|[A-Za-z0-9_-]{1,100}/[1-9][0-9]*)\\.(jpg|png)"))throw new ResponseStatusException(HttpStatus.NOT_FOUND);
  Path path=uploads.resolve(fileName);
  if(!Files.isRegularFile(path))throw new ResponseStatusException(HttpStatus.NOT_FOUND);
  return path;
 }
 private static ResponseStatusException bad(String msg){return new ResponseStatusException(HttpStatus.BAD_REQUEST,msg);}
}
