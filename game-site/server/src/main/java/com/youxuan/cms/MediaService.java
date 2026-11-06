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
 public Upload store(byte[] bytes,String name){
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
    String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(normalized));
    String fileName=hash+"."+ext;
    Files.createDirectories(uploads);
    Path target=uploads.resolve(fileName);
    if(!Files.exists(target)){
     Path temp=Files.createTempFile(uploads,".upload-",".tmp");
     try{Files.write(temp,normalized);try{Files.move(temp,target,StandardCopyOption.ATOMIC_MOVE);}catch(AtomicMoveNotSupportedException e){Files.move(temp,target,StandardCopyOption.REPLACE_EXISTING);}}finally{Files.deleteIfExists(temp);}
    }
    return new Upload("/media/"+fileName,name==null?fileName:Path.of(name.replace('\\','/')).getFileName().toString());
   }finally{reader.dispose();}
  }catch(ResponseStatusException e){throw e;}catch(IOException e){throw bad("图片损坏或服务器存储不可用");}catch(java.security.NoSuchAlgorithmException e){throw new IllegalStateException(e);}
 }
 public Path file(String fileName){
  if(!fileName.matches("[a-f0-9]{64}\\.(jpg|png)"))throw new ResponseStatusException(HttpStatus.NOT_FOUND);
  Path path=uploads.resolve(fileName);
  if(!Files.isRegularFile(path))throw new ResponseStatusException(HttpStatus.NOT_FOUND);
  return path;
 }
 private static ResponseStatusException bad(String msg){return new ResponseStatusException(HttpStatus.BAD_REQUEST,msg);}
}
