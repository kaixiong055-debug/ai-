package com.youxuan.cms;

import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MaxUploadSizeExceededException;
import org.springframework.web.server.ResponseStatusException;
import java.util.Map;

@RestControllerAdvice(annotations=RestController.class)
public class ApiErrors {
 @ExceptionHandler(ResponseStatusException.class) public ResponseEntity<Map<String,String>> response(ResponseStatusException e){return ResponseEntity.status(e.getStatusCode()).body(Map.of("message",e.getReason()==null?"请求失败":e.getReason()));}
 @ExceptionHandler(HttpMessageNotReadableException.class) public ResponseEntity<Map<String,String>> malformed(){return ResponseEntity.badRequest().body(Map.of("message","提交内容格式不正确，请检查输入"));}
 @ExceptionHandler(MaxUploadSizeExceededException.class) public ResponseEntity<Map<String,String>> oversized(){return ResponseEntity.status(413).body(Map.of("message","上传文件过大，ZIP 上限 64 MB，图片上限 12 MB，JSON 上限 2 MB"));}
}
