package com.youxuan.cms;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.io.IOException;
@RestController
public class ImportController {
 private final ImportService importer;public ImportController(ImportService importer){this.importer=importer;}
 @PostMapping("/api/admin/import") public Game importGame(@RequestParam("json") MultipartFile json,@RequestParam("zip") MultipartFile zip,@RequestParam(value="gameId",defaultValue="")String gameId)throws IOException{
  if(json.getSize()>2*1024*1024||zip.getSize()>64L*1024*1024)throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"JSON 上限 2MB，ZIP 上限 64MB");
  try(var input=zip.getInputStream()){return importer.importGame(json.getBytes(),input,gameId);}
 }
}
