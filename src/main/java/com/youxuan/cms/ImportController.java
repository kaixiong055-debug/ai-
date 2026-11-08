package com.youxuan.cms;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import java.io.IOException;
@RestController
public class ImportController {
 private final ImportService importer;private final BatchImportService batch;private final com.fasterxml.jackson.databind.ObjectMapper mapper;public ImportController(ImportService importer,BatchImportService batch,com.fasterxml.jackson.databind.ObjectMapper mapper){this.importer=importer;this.batch=batch;this.mapper=mapper;}
 @PostMapping("/api/admin/import/plan") public java.util.List<BatchImportService.Item> plan(@RequestParam("json")MultipartFile json,@RequestParam("filenames")String filenames)throws IOException{if(json.getSize()>2*1024*1024||filenames.length()>2*1024*1024)throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"匹配资料过大");return batch.plan(json.getBytes(),mapper.readValue(filenames,new com.fasterxml.jackson.core.type.TypeReference<java.util.List<String>>(){}));}
 @PostMapping("/api/admin/import") public Game importGame(@RequestParam("json") MultipartFile json,@RequestParam("zip") MultipartFile zip,@RequestParam(value="gameId",defaultValue="")String gameId)throws IOException{
  if(json.getSize()>2*1024*1024||zip.getSize()>64L*1024*1024)throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"JSON 上限 2MB，ZIP 上限 64MB");
  try(var input=zip.getInputStream()){return importer.importGame(json.getBytes(),input,gameId);}
 }
}
