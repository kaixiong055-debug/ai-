package com.youxuan.cms;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.HttpStatus;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin")
public class AdminApiController {
 private final GameService games;
 public AdminApiController(GameService games){this.games=games;}
 @GetMapping("/session") public Map<String,String> session(HttpServletRequest request,Authentication auth){CsrfToken csrf=(CsrfToken)request.getAttribute(CsrfToken.class.getName());return Map.of("username",auth.getName(),"token",csrf.getToken(),"headerName",csrf.getHeaderName());}
 @GetMapping("/games")public List<Game> list(@RequestParam(defaultValue="")String q,@RequestParam(defaultValue="")String status){return games.list(q,status);}
 @GetMapping("/games/{id}")public Game get(@PathVariable String id){return games.find(id).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"游戏不存在"));}
 @PostMapping("/games")@ResponseStatus(HttpStatus.CREATED)public Game create(@RequestBody Game game){if(game.id!=null&&!game.id.isBlank()&&games.find(game.id).isPresent())throw new ResponseStatusException(HttpStatus.CONFLICT,"游戏ID已存在");if(game.revision!=0)throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"新游戏 revision 必须为 0");return games.save(game);}
 @PutMapping("/games/{id}")public Game update(@PathVariable String id,@RequestBody Game game){get(id);if(game.id!=null&&!game.id.isBlank()&&!id.equals(game.id))throw new ResponseStatusException(HttpStatus.BAD_REQUEST,"不能修改游戏ID");game.id=id;return games.save(game);}
 @DeleteMapping("/games/{id}")@ResponseStatus(HttpStatus.NO_CONTENT)public void delete(@PathVariable String id,@RequestParam long revision){games.delete(id,revision);}
 @GetMapping("/settings")public SiteSettings settings(){return games.settings();}
 @PutMapping("/settings")public SiteSettings settings(@RequestBody SiteSettings settings){return games.saveSettings(settings);}
}
