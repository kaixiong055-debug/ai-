package com.youxuan.cms;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.nio.file.Files;
import java.awt.image.BufferedImage;
import javax.imageio.ImageIO;
import java.io.ByteArrayOutputStream;
import static org.assertj.core.api.Assertions.*;

class MediaServiceTest {
 @TempDir Path dir;
 static byte[] png() throws Exception {var out=new ByteArrayOutputStream();ImageIO.write(new BufferedImage(12,15,BufferedImage.TYPE_INT_RGB),"png",out);return out.toByteArray();}
 @Test void storesValidatedImagesByContentAndDeduplicates() throws Exception {
  var service=new MediaService(dir.toString());
  var first=service.store(png(),"../../bad.png");var second=service.store(png(),"copy.png");
  assertThat(first.url()).isEqualTo(second.url()).matches("/media/[a-f0-9]{64}\\.png");
  assertThat(service.file(first.url().substring(7))).exists();
  try(var files=Files.list(dir.resolve("uploads"))){assertThat(files.count()).isEqualTo(1);}
 }
 @Test void rejectsSvgScriptPayloadAndPathTraversal() {
  var service=new MediaService(dir.toString());
  assertThatThrownBy(()->service.store("<svg onload='alert(1)'/>".getBytes(),"fake.png")).hasMessageContaining("图片");
  assertThatThrownBy(()->service.file("../../application.yml")).isInstanceOf(RuntimeException.class);
 }
 @Test void separatesGamesAndNumbersImagesWithDeduplication()throws Exception {
  var media=new MediaService(dir.toString());
  assertThat(media.store(png(),"icon.png","14545").url()).isEqualTo("/media/14545/1.png");
  assertThat(media.store(png(),"copy.png","14545").url()).isEqualTo("/media/14545/1.png");
  assertThat(media.store(png(),"other.png","14604").url()).isEqualTo("/media/14604/1.png");
  var out=new ByteArrayOutputStream();ImageIO.write(new BufferedImage(20,20,BufferedImage.TYPE_INT_RGB),"png",out);
  assertThat(media.store(out.toByteArray(),"next.png","14545").url()).isEqualTo("/media/14545/2.png");
  assertThat(media.file("14545/2.png")).exists();
  assertThatThrownBy(()->media.store(png(),"x.png","../bad")).hasMessageContaining("游戏ID");
 }
 @Test void migrationPreservesOriginalBytesAndSharedLegacyUrls()throws Exception {
  var media=new MediaService(dir.toString());String old=media.store(png(),"old.png").url();
  assertThat(media.rehome("14545",old)).isEqualTo("/media/14545/1.png");
  assertThat(media.rehome("14604",old)).isEqualTo("/media/14604/1.png");
  assertThat(media.rehome("14545",old)).isEqualTo("/media/14545/1.png");
  assertThat(Files.readAllBytes(media.file("14545/1.png"))).isEqualTo(Files.readAllBytes(media.file(old.substring(7))));
 }
}
