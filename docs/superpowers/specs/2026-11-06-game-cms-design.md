# 游戏推广站 Java CMS

用户已认可现有页面视觉，授权选择前端技术并完成系统，在新分支交付。采用 Spring Boot 3 / Java 17+、Thymeleaf 服务端 HTML、原生 JS 管理界面，单个 JAR 部署。后台管理游戏文案、图片上传/链接、视频直链、下载渠道链接和每游戏 SEO。保留 JSON + ZIP 导入需求，导入生成草稿。无可用服务器凭据，本轮交付可部署服务和 Linux/宝塔配置，不宣称已上线。

独立分支 feat/game-cms-java，独立工作目录 /workspace/game-cms。旧静态预览保持可用。

数据库默认服务器 H2 文件，支持 PostgreSQL 环境变量切换；图片文件位于服务器 data/uploads，视频使用 HTTPS 直链，不下载视频，不将第三方 Cookie/渠道后台数据发布。管理员由环境变量配置，强制密码，登录 session/CSRF/限速，所有管理 API 需认证。生产 HTTPS 反向代理，备份数据库与 uploads。

公开页 /games/{slug}/，SSR 全正文/标题/meta/OG/JSON-LD/FAQ/图片 alt，首页有链接与搜索，sitemap 仅已发布且允许索引游戏，草稿404、登录预览noindex，域名未设置不索引。自动 SEO 可逐字段覆盖，URL slug 创建后可编辑直到首次发布，发布后锁定避免失效链接。不存在虚构评分、礼包、安装量。

游戏 fields: id, slug, name, subtitle, summary, description, category, platform, version, iconUrl, heroUrl, downloadUrl, introUrl, seoTitle, seoDescription, seoKeywords, ogImage (String); noindex, published (boolean); tags (List<String>); screenshots (List<Picture(url,alt)>); videos (List<Video(title,url,poster)>); features/benefits (List<Section(title,text)>); faqs (List<Faq(question,answer)>); revision(long); createdAt/updatedAt(String). 新 id UUID；导入使用源 game_id/id。slug 小写ASCII字母数字横线，默认id。

SiteSettings fields: siteName, siteUrl, seoTitle, seoDescription, footerText, icpNumber (String), allowIndexing(boolean)。siteUrl 只支持 HTTPS 根域名。默认游选，空域名和false indexing。

GameService: list(String q,String status), find(String id):Optional<Game>, publishedBySlug(String):Optional<Game>, save(Game):Game, delete(String,long), settings():SiteSettings, saveSettings(SiteSettings):SiteSettings。保存按 revision 防覆盖；合法 HTTPS 外链及 /media/ 文件链接；安全纯文本渲染。

API: GET /api/admin/session -> {username,token,headerName}; GET /api/admin/games?q=&status= -> Game[]; GET /api/admin/games/{id}->Game; POST /api/admin/games (Game JSON create); PUT /api/admin/games/{id} (Game JSON save); DELETE /api/admin/games/{id}?revision=N ->204; GET/PUT /api/admin/settings; POST /api/admin/media (multipart file) -> {url,name}; POST /api/admin/import (multipart json file optional for selected source, zip file, gameId text) -> Game. 默认 JSON 支持此前 result.data 格式；ZIP仅导入文本和图片，忽略视频（提示填写视频链接）；禁止路径穿越、限制解压大小/条目、图像格式校验。

公开模板 model: game(Game), settings(SiteSettings), seo(Map: title,description,keywords,canonical,image,robots,jsonLd), preview(boolean); 首页另 games(List<Game>), q(String)。公开页面无需 JS 即可阅读与跳转。

管理UI /admin, 登录 /login，POST /logout。后台有游戏列表与新建编辑、图片排序/替代文字、视频链接/封面/标题、文案段落和FAQ编辑、SEO搜索预览、草稿预览与发布、全站设置、导入。
