package com.youxuan.cms;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import java.util.*;
import static org.assertj.core.api.Assertions.*;
@SpringBootTest(properties={"spring.datasource.url=jdbc:h2:mem:batch;DB_CLOSE_DELAY=-1","cms.admin.password=BatchOnly-2026-test","cms.data-dir=${java.io.tmpdir}/cms-batch-test","cms.demo.enabled=false"})
class BatchImportTest {
 @Autowired BatchImportService batch;@Autowired GameService games;@Autowired ImportService importer;
 byte[] json(String text){return text.getBytes(java.nio.charset.StandardCharsets.UTF_8);}
 @Test void matchesChineseMaterialNameAndIdAndReportsMissing(){var rows=batch.plan(json("[{\"id\":\"1\",\"name\":\"小小驯龙师-首充送霸王龙\"},{\"id\":\"2\",\"name\":\"第二款\"},{\"id\":\"3\",\"name\":\"缺少素材\"}]"),List.of("目录/《小小驯龙师-首充送霸王龙》游戏素材.zip","子目录/2.zip"));assertThat(rows).extracting(BatchImportService.Item::status).containsExactly("ready","ready","error");assertThat(rows.get(0).fileIndex()).isZero();}
 @Test void skipsExistingWithoutChangingContent()throws Exception{Game g=new Game();g.id="existing";g.name="已编辑";games.save(g);var rows=batch.plan(ImportServiceTest.source("existing"),List.of("existing.zip"));assertThat(rows.get(0).status()).isEqualTo("skipped");assertThat(games.find("existing").orElseThrow().name).isEqualTo("已编辑");}
 @Test void ambiguousAndDuplicateFilesNeverGuess(){var rows=batch.plan(json("[{\"id\":\"a\",\"name\":\"同名\"},{\"id\":\"b\",\"name\":\"同名\"}]"),List.of("同名.zip"));assertThat(rows.stream().filter(r->r.status().equals("ready"))).isEmpty();rows=batch.plan(ImportServiceTest.source("duplicate"),List.of("a/duplicate.zip","b/duplicate.zip"));assertThat(rows.get(0).status()).isEqualTo("error");}
 @Test void rerunAfterPartialSuccessSkipsCompletedAndRetriesRemaining()throws Exception{byte[] data=json("[{\"id\":\"done\",\"name\":\"完成\"},{\"id\":\"todo\",\"name\":\"待处理\"}]");importer.importGame(data,new java.io.ByteArrayInputStream(ImportServiceTest.zip("游戏简介.txt",json("游戏介绍"))),"done");var rows=batch.plan(data,List.of("done.zip","todo.zip"));assertThat(rows.get(0).status()).isEqualTo("skipped");assertThat(rows.get(1).status()).isEqualTo("ready");assertThat(games.find("todo")).isEmpty();}
 @Test void gameNamesEndingInMaterialWordRemainIntact(){var rows=batch.plan(json("{\"id\":\"material\",\"name\":\"坏素材\"}"),List.of("《坏素材》游戏素材.zip"));assertThat(rows.get(0).status()).isEqualTo("ready");}
}
