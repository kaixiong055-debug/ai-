package com.youxuan.cms;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import static org.assertj.core.api.Assertions.*;
@SpringBootTest(properties={"spring.datasource.url=jdbc:h2:mem:mediamigration;DB_CLOSE_DELAY=-1","cms.admin.password=test-admin-password-123","cms.data-dir=${java.io.tmpdir}/cms-media-migration-test","cms.demo.enabled=false"})
class MediaMigrationTest {
 @Autowired GameService games;@Autowired MediaService media;@Autowired MediaMigration migration;@Autowired JdbcTemplate db;@Autowired ObjectMapper json;
 @Test void updatesStoredReferencesAndIsIdempotent()throws Exception{
  Game g=new Game();g.id="migrate-test";g.name="旧游戏";g=games.save(g);
  String old=media.store(MediaServiceTest.png(),"old.png").url();g.iconUrl=old;g.heroUrl=old;g.screenshots=java.util.List.of(new Game.Picture(old,"截图"));g.videos=java.util.List.of(new Game.Video("视频","https://cdn.example.com/game.mp4",old));
  db.update("UPDATE cms_games SET payload=? WHERE id=?",json.writeValueAsString(g),g.id);
  migration.run(null);Game migrated=games.find(g.id).orElseThrow();
  assertThat(migrated.iconUrl).isEqualTo("/media/migrate-test/1.png");assertThat(migrated.screenshots.get(0).url()).isEqualTo(migrated.iconUrl);assertThat(migrated.videos.get(0).poster()).isEqualTo(migrated.iconUrl);
  migration.run(null);assertThat(games.find(g.id).orElseThrow().revision).isEqualTo(migrated.revision);
 }
}
