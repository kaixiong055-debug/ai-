package com.youxuan.cms;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;
class AiSeoTest {
 final ObjectMapper json=new ObjectMapper();
 @Test void returnsOnlyAllowedFields()throws Exception{
  var result=AiSeoController.parse(json,"{\"seoTitle\":\"恐龙游戏\",\"seoDescription\":\"收集恐龙\",\"faqs\":[{\"question\":\"玩法？\",\"answer\":\"收集恐龙\"}],\"published\":true}");
  assertThat(result).containsEntry("seoKeywords","").doesNotContainKey("published");assertThat((java.util.List<?>)result.get("faqs")).hasSize(1);
 }
 @Test void rejectsInvalidOrIncompleteResults(){
  for(String input:new String[]{"{}","null","{\"faqs\":[]}","not json"})assertThatThrownBy(()->AiSeoController.parse(json,input)).isInstanceOf(Exception.class);
 }
 @Test void missingKeyFailsClearlyWithoutNetwork(){assertThatThrownBy(()->new AiSeoController(json,"").generate(new Game())).hasMessageContaining("DEEPSEEK_API_KEY");}
}
