package com.youxuan.cms;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import java.time.Instant;
import java.util.*;

@Service
public class GameService {
 private final JdbcTemplate db;private final ObjectMapper json;
 public GameService(JdbcTemplate db,ObjectMapper json){this.db=db;this.json=json;}
 public List<Game> list(String q,String status){
  String needle=q==null?"":q.trim().toLowerCase(Locale.ROOT);
  if(!Set.of("","published","draft").contains(status==null?"":status))throw bad("无效的发布状态");
  return db.query("SELECT payload FROM cms_games ORDER BY updated_at DESC, id",(rs,n)->readGame(rs.getString(1))).stream().filter(g->(status==null||status.isBlank()||g.published==status.equals("published"))&&(needle.isBlank()||(g.name+" "+g.summary+" "+g.category+" "+g.id).toLowerCase(Locale.ROOT).contains(needle))).toList();
 }
 public Optional<Game> find(String id){return db.query("SELECT payload FROM cms_games WHERE id=?",(rs,n)->readGame(rs.getString(1)),id).stream().findFirst();}
 public Optional<Game> publishedBySlug(String slug){return db.query("SELECT payload FROM cms_games WHERE slug=? AND published=TRUE",(rs,n)->readGame(rs.getString(1)),slug).stream().findFirst();}
 @Transactional
 public Game save(Game input){
  if(input==null)throw bad("缺少游戏数据");Game g=json.convertValue(input,Game.class);
  g.id=text(g.id,100,"游戏ID");if(g.id.isEmpty())g.id=UUID.randomUUID().toString();
  if(!g.id.matches("[A-Za-z0-9_-]{1,100}"))throw bad("游戏ID格式不正确");
  Optional<Game> previous=find(g.id);boolean fresh=previous.isEmpty();
  if(fresh&&g.revision!=0)throw conflict("记录已删除或不存在，请重新加载");
  if(!fresh&&previous.get().revision!=g.revision)throw conflict("内容已被更新，请重新加载后保存");
  g.slug=text(g.slug,100,"页面URL");if(g.slug.isEmpty())g.slug=g.id.toLowerCase(Locale.ROOT);
  if(!g.slug.matches("[a-z0-9]+(?:-[a-z0-9]+)*")||g.slug.length()>100)throw bad("URL 标识仅支持小写字母、数字和中间的短横线");
  boolean locked=!fresh&&Boolean.TRUE.equals(db.queryForObject("SELECT slug_locked FROM cms_games WHERE id=?",Boolean.class,g.id));
  if(locked&&!g.slug.equals(previous.get().slug))throw conflict("首次发布后 URL 已锁定，避免搜索链接失效");
  normalize(g);
  if(g.published&&(g.name.isBlank()||g.description.isBlank()||g.iconUrl.isBlank()||g.heroUrl.isBlank()||g.downloadUrl.isBlank()))throw bad("发布前请填写游戏名称、详细介绍、图标、主视觉和下载链接");
  String now=Instant.now().toString();g.createdAt=fresh?now:previous.get().createdAt;g.updatedAt=now;long oldRevision=g.revision;g.revision=oldRevision+1;
  try{
   if(fresh)db.update("INSERT INTO cms_games(id,slug,payload,published,slug_locked,revision,updated_at) VALUES(?,?,?,?,?,?,?)",g.id,g.slug,write(g),g.published,g.published,g.revision,now);
   else if(db.update("UPDATE cms_games SET slug=?,payload=?,published=?,slug_locked=?,revision=?,updated_at=? WHERE id=? AND revision=?",g.slug,write(g),g.published,locked||g.published,g.revision,now,g.id,oldRevision)!=1)throw conflict("内容已被更新，请重新加载后保存");
  }catch(DuplicateKeyException e){throw conflict("游戏ID或页面URL已存在，请使用其他标识");}
  return g;
 }
 @Transactional
 public void delete(String id,long revision){Game g=find(id).orElseThrow(()->new ResponseStatusException(HttpStatus.NOT_FOUND,"游戏不存在"));if(g.revision!=revision)throw conflict("内容已被更新，请重新加载后删除");if(db.update("DELETE FROM cms_games WHERE id=? AND revision=?",id,revision)!=1)throw conflict("内容已被更新，请重新加载后删除");}
 public SiteSettings settings(){return db.query("SELECT payload FROM cms_settings WHERE id=1",(rs,n)->read(rs.getString(1),SiteSettings.class)).stream().findFirst().orElseGet(SiteSettings::new);}
 @Transactional
 public SiteSettings saveSettings(SiteSettings input){
  if(input==null)throw bad("缺少网站设置");SiteSettings s=json.convertValue(input,SiteSettings.class);s.siteName=text(s.siteName,80,"网站名称");if(s.siteName.isEmpty())throw bad("请填写网站名称");s.siteUrl=UrlPolicy.site(s.siteUrl);s.seoTitle=text(s.seoTitle,150,"网站标题");s.seoDescription=text(s.seoDescription,500,"网站描述");s.footerText=text(s.footerText,2000,"页脚");s.icpNumber=text(s.icpNumber,100,"备案号");if(s.allowIndexing&&s.siteUrl.isEmpty())throw bad("允许索引前请填写正式网站域名");
  if(db.update("UPDATE cms_settings SET payload=? WHERE id=1",write(s))==0){try{db.update("INSERT INTO cms_settings(id,payload) VALUES(1,?)",write(s));}catch(DuplicateKeyException e){throw conflict("网站设置已被更新，请重试");}}return s;
 }
 private void normalize(Game g){
  g.name=text(g.name,150,"游戏名称");g.subtitle=text(g.subtitle,200,"副标题");g.summary=text(g.summary,500,"游戏摘要");g.description=text(g.description,30000,"详细介绍");g.category=text(g.category,80,"分类");g.platform=text(g.platform,80,"平台");g.version=text(g.version,80,"版本");g.seoTitle=text(g.seoTitle,150,"SEO标题");g.seoDescription=text(g.seoDescription,500,"SEO描述");g.seoKeywords=text(g.seoKeywords,500,"SEO关键词");
  g.iconUrl=UrlPolicy.media(g.iconUrl);g.heroUrl=UrlPolicy.media(g.heroUrl);g.ogImage=UrlPolicy.media(g.ogImage);g.downloadUrl=UrlPolicy.external(g.downloadUrl);g.introUrl=UrlPolicy.external(g.introUrl);
  g.tags=items(g.tags,20,"标签").stream().map(s->text(s,50,"标签")).filter(s->!s.isBlank()).distinct().toList();
  g.screenshots=items(g.screenshots,40,"图片").stream().map(p->{if(p==null)throw bad("图片不可为空");String url=UrlPolicy.media(p.url());if(url.isBlank())throw bad("请填写图片链接");return new Game.Picture(url,text(p.alt(),200,"图片说明"));}).toList();
  g.videos=items(g.videos,12,"视频").stream().map(v->{if(v==null)throw bad("视频不可为空");String url=UrlPolicy.external(v.url());if(url.isBlank())throw bad("请填写视频链接");return new Game.Video(text(v.title(),150,"视频标题"),url,UrlPolicy.media(v.poster()));}).toList();
  g.features=sections(g.features,"玩法亮点");g.benefits=sections(g.benefits,"福利说明");
  g.faqs=items(g.faqs,30,"常见问题").stream().map(f->{if(f==null)throw bad("问题不可为空");String question=text(f.question(),300,"问题");String answer=text(f.answer(),3000,"答案");if(question.isEmpty()||answer.isEmpty())throw bad("常见问题与答案请成对填写");return new Game.Faq(question,answer);}).toList();
 }
 private List<Game.Section> sections(List<Game.Section> sections,String label){return items(sections,30,label).stream().map(s->{if(s==null)throw bad(label+"不可为空");return new Game.Section(text(s.title(),150,label),text(s.text(),5000,label));}).toList();}
 private <T> List<T> items(List<T> input,int max,String name){if(input==null)return List.of();if(input.size()>max)throw bad(name+"最多 "+max+" 项");return input;}
 private String text(String input,int max,String label){String s=input==null?"":input.trim();if(s.length()>max)throw bad(label+"不能超过 "+max+" 个字符");if(s.indexOf('\0')>=0)throw bad(label+"含有无效字符");return s;}
 private Game readGame(String data){return read(data,Game.class);}
 private <T>T read(String data,Class<T> type){try{return json.readValue(data,type);}catch(JsonProcessingException e){throw new IllegalStateException("数据库记录格式无效",e);}}
 private String write(Object data){try{return json.writeValueAsString(data);}catch(JsonProcessingException e){throw new IllegalStateException("无法保存记录",e);}}
 private ResponseStatusException bad(String message){return new ResponseStatusException(HttpStatus.BAD_REQUEST,message);}
 private ResponseStatusException conflict(String message){return new ResponseStatusException(HttpStatus.CONFLICT,message);}
}
