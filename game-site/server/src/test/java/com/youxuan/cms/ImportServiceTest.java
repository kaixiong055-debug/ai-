package com.youxuan.cms;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.zip.*;
import static org.assertj.core.api.Assertions.*;

@SpringBootTest(properties={"spring.datasource.url=jdbc:h2:mem:imports;DB_CLOSE_DELAY=-1","cms.admin.password=test-admin-password-123","cms.data-dir=${java.io.tmpdir}/cms-import-test","cms.demo.enabled=false"})
class ImportServiceTest {
 @Autowired ImportService importer;
 @Autowired GameService games;
 static byte[] zip(String name,byte[] data)throws Exception {var b=new ByteArrayOutputStream();try(var z=new ZipOutputStream(b)){z.putNextEntry(new ZipEntry(name));z.write(data);z.closeEntry();}return b.toByteArray();}
 static byte[] source(String id){return ("{\"result\":{\"data\":[{\"game_id\":\""+id+"\",\"name\":\"测试恐龙\",\"pkg_url\":\"https://m.3387.com/s/test?d=1\",\"activity_url\":\"https://m.3387.com/s/test\",\"level_1_rate\":99,\"zip_url\":\"PRIVATE\"}]}}").getBytes(StandardCharsets.UTF_8);}
 @Test void importsSourceAndZipAsDraftWithoutPrivateFields()throws Exception{
  Game g=importer.importGame(source("import-one"),new ByteArrayInputStream(zip("游戏简介.txt","真实介绍".getBytes(StandardCharsets.UTF_8))),"import-one");
  assertThat(g.published).isFalse();assertThat(g.description).isEqualTo("真实介绍");assertThat(g.downloadUrl).endsWith("?d=1");
  assertThat(new ObjectMapper().writeValueAsString(g)).doesNotContain("PRIVATE","level_1_rate");
  assertThat(games.find(g.id)).isPresent();
  assertThatThrownBy(()->importer.importGame(source("import-one"),new ByteArrayInputStream(zip("游戏简介.txt",new byte[0])),"import-one")).hasMessageContaining("已存在");
 }
 @Test void rejectsTraversalBeforeSavingGame()throws Exception{
  assertThatThrownBy(()->importer.importGame(source("bad-zip"),new ByteArrayInputStream(zip("../escape.txt","x".getBytes())),"bad-zip")).hasMessageContaining("路径");
  assertThat(games.find("bad-zip")).isEmpty();
 }
 @Test void mapsActualImageFoldersAndDeduplicatesGallery()throws Exception {
  var b=new ByteArrayOutputStream();try(var z=new ZipOutputStream(b)){for(String p:new String[]{"游戏素材/游戏icon/001.jpg","游戏素材/banner/001.jpg","游戏素材/游戏截图/001.jpg","游戏素材/游戏截图/002.jpg"}){z.putNextEntry(new ZipEntry(p));z.write(MediaServiceTest.png());z.closeEntry();}}
  Game g=importer.importGame(source("with-images"),new ByteArrayInputStream(b.toByteArray()),"with-images");
  assertThat(g.iconUrl).startsWith("/media/");assertThat(g.heroUrl).startsWith("/media/");assertThat(g.screenshots).hasSize(1);
 }
 @Test void directoryPayloadCannotBypassArchiveLimit()throws Exception {
  var b=new ByteArrayOutputStream();try(var z=new ZipOutputStream(b)){z.putNextEntry(new ZipEntry("hidden/"));byte[] block=new byte[1024*1024];for(int i=0;i<129;i++)z.write(block);z.closeEntry();}
  assertThatThrownBy(()->importer.importGame(source("directory-bomb"),new ByteArrayInputStream(b.toByteArray()),"directory-bomb")).hasMessageContaining("128MB");
  assertThat(games.find("directory-bomb")).isEmpty();
 }
}
