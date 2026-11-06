package com.youxuan.cms;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;
import java.io.IOException;
import java.time.Duration;

@RestController
public class MediaController {
 private final MediaService media;
 public MediaController(MediaService media){this.media=media;}
 @PostMapping("/api/admin/media") public MediaService.Upload upload(@RequestParam("file") MultipartFile file)throws IOException{
  if(file.getSize()>MediaService.MAX_IMAGE_BYTES)throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"图片不能超过 12MB");
  return media.store(file.getBytes(),file.getOriginalFilename());
 }
 @GetMapping("/media/{name}") public ResponseEntity<Resource> file(@PathVariable String name){
  return ResponseEntity.ok().cacheControl(CacheControl.maxAge(Duration.ofDays(365)).cachePublic().immutable())
   .contentType(name.endsWith(".jpg")?MediaType.IMAGE_JPEG:MediaType.IMAGE_PNG).header("X-Content-Type-Options","nosniff")
   .body(new FileSystemResource(media.file(name)));
 }
}
