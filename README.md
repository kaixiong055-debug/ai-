# 游选 · Java 游戏站与管理后台

保留已确认的游戏落地页效果，提供可登录管理的服务器版本。Java 17+，Spring Boot 3.5，Thymeleaf 输出完整 HTML，后台原生 JavaScript；无需 Node、Docker 或单独前端构建。

## 已实现

- `/admin` 游戏管理：创建、编辑、删除、搜索、草稿、预览、发布和下线。
- 服务器保存文字和 SEO；图片可上传或填写 HTTPS 地址，截图可排序、设替代文字。上传 JPG/PNG/GIF 会重编码去除附带内容；GIF取首帧。
- 视频填写 HTTPS 直链（建议 MP4/H.264）；可配置多个视频标题和封面，播放器点击后才请求文件。不抓取视频站页面或自动下载视频。
- 游戏玩法、福利、FAQ、推广下载地址、介绍页地址均可配置。
- 每游戏唯一 `/games/{slug}/`，SSR正文、独立title/description/keywords、canonical、OG、结构化数据，自动SEO可覆盖。首次发布后锁定URL；正文仍可随时修改。
- 动态 sitemap.xml / robots.txt：只包含已发布且允许索引的游戏；未配置正式域名默认noindex，后台、预览和草稿不参与索引。搜索结果页noindex。
- JSON + ZIP导入草稿：支持3387 `result.data`列表（填写game_id）和已有规范化JSON；按“游戏icon/banner/游戏截图/简介/福利”文件名匹配。不会导入佣金、签名ZIP链接等后台资料；重复ID拒绝覆盖。ZIP视频不上传，JSON里有效视频URL可导入，否则在编辑器填写直链。
- 管理端 session登录、CSRF、登录失败限制、内容转义、URL校验、上传限制、并发编辑冲突提示。

## 本机运行

准备 Java 17+ 和 Maven 3.9+：

```bash
# 在本项目根目录执行
mvn clean verify
export GAME_ADMIN_USERNAME=admin
read -rsp '请输入管理员密码（至少12字符）: ' GAME_ADMIN_PASSWORD; echo
export GAME_ADMIN_PASSWORD
export CMS_DEMO_ENABLED=true  # 可选：首次创建小小驯龙师草稿及真实图片
./start.sh
```

访问 `http://127.0.0.1:8080/admin`。后台输入上面设置的账号密码。示例处于草稿，先编辑、预览，再发布。默认站点无域名，因此保持noindex。公网正式部署完成后在“站点设置”填写真实HTTPS根域名，检查游戏页面后启用索引。

数据默认写入运行目录的 `data/cms.mv.db` 与 `data/uploads/`；应用更新不得覆盖 data。示例初始不配置视频，可直接输入自己的视频CDN链接。

## Linux / 宝塔部署

交付部署包已经包含 `game-cms.jar`，服务器只需 Java 17+ 运行时。源码构建产物为 `target/game-cms-1.0.0.jar`。

1. 准备域名并解析到服务器；宝塔创建该域名站点，申请SSL证书，启用HTTPS。
2. 将 `game-cms.jar`、deploy、start.sh 放到 `/www/wwwroot/game-cms/`。创建普通系统用户 `gamecms`（已有则复用），创建data目录并授权：

```bash
sudo useradd --system --no-create-home --shell /usr/sbin/nologin gamecms
sudo mkdir -p /www/wwwroot/game-cms/data
sudo chown -R gamecms:gamecms /www/wwwroot/game-cms
sudo cp /www/wwwroot/game-cms/deploy/env.example /www/wwwroot/game-cms/.env
sudo chmod 600 /www/wwwroot/game-cms/.env
```

3. 编辑 `.env`：替换管理员密码，使用至少12字符，最多72字节；保留 `COOKIE_SECURE=true`（HTTPS必需）。使用宝塔终端或SSH修改，不把密码贴到Git。
4. `deploy/game-cms.service` 中的Java路径须与服务器一致（`command -v java`）；复制为 `/etc/systemd/system/game-cms.service` 后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now game-cms
sudo systemctl status game-cms
```

5. 宝塔反向代理目标 `http://127.0.0.1:8080`，关闭缓存；`deploy/nginx-location.conf` 提供对应location参数和上传上限。**不要将项目/data/.env目录直接设为可浏览的网站目录**，所有请求转发给Java。安全组只开放80/443，8080绑定本机。
6. 打开 `https://你的域名/admin`，登录→站点设置→填写名称和HTTPS根域名→新增/导入游戏→编辑视频/图片/文案/SEO→预览→发布→检查前台→启用搜索索引。

检查日志：`journalctl -u game-cms -n 100 --no-pager`。不在日志中输出管理员密码和JSON原始渠道数据。后台接口不对前台页面开放。

## 数据库、备份与更新

默认H2持久化数据库在服务器磁盘，适合单实例初期运营；不要多进程同时打开同一个H2文件。可用DB_URL/DB_USER/DB_PASSWORD指向PostgreSQL，应用自动建表；切换数据库不会自动搬迁旧数据，应先做单独数据迁移。

备份H2：先 `systemctl stop game-cms`，完整复制 `data/`（数据库和图片）及私密保存的`.env`，再启动。PostgreSQL使用pg_dump，并同步备份uploads。备份必须带访问权限，不能放公开下载目录。

更新：备份→停止服务→替换JAR→启动服务；保留data和.env。第一版不自动清理未引用图片，删除游戏不会误删其他游戏共享图片，备份时保留uploads。

首次登录失败限制按服务器观察到的连接地址计数，反代下可能共享额度：12次失败后15分钟解锁。单管理员第一版，账号和密码在服务环境配置中修改并重启生效。

## SEO与微信使用

页面无需JavaScript即可读取全部正文和下载链接；手机、电脑、微信公众号内置浏览器可以访问同一URL。微信可能限制APK下载，页面显示“在系统浏览器打开”提示。微信自定义分享卡片还需要公众号JS-SDK授权，这一版不伪造已授权分享。

域名设置支持根域名，不支持部署在 `/foo` 子路径。`canonical`始终由配置的正式域名生成，避免被伪造Host头影响。site map不保证搜索引擎收录或排名；上线后将域名和sitemap提交对应搜索站长工具。

后台图片外链需允许跨站显示，视频链接需支持浏览器播放及Range请求；此环境未实测用户的第三方CDN、微信真机或实际宝塔服务器。

## 验证

`mvn test` 运行认证、CRUD、数据验证、修订冲突、导入、图片安全和SEO测试。浏览器验收和当前版本验证结论见 `VERIFICATION.md`。

## DeepSeek 自动生成 SEO 与常见问题

在 `application.yml` 直接配置密钥：

```yaml
deepseek:
  api-key: "你的DeepSeek密钥"
```

源码配置文件为 `src/main/resources/application.yml`。已部署 JAR 时，将 `deploy/application.yml` 复制到 `game-cms.jar` 同目录，填写密钥并重启服务即可，无需重新打包。打开后台→编辑游戏→独立 SEO→「AI 生成 SEO 和常见问题」。先填写游戏名称、介绍和实际福利；生成会替换编辑框中的SEO标题、描述、关键词及FAQ，检查后点击保存才会更新数据库/公开页面。

Java后端调用官方 `https://api.deepseek.com/chat/completions`，模型 `deepseek-chat`，60秒超时，不自动重试；按你的DeepSeek账户计费。只发送游戏文字资料，不发送管理员密码、图片文件或推广链接。Key不发给浏览器、不写普通日志。服务器需能通过HTTPS访问 api.deepseek.com。未配置密钥、额度不足、限流、超时会显示中文错误，保留原内容。AI可能出错，请检查事实与活动条件。

## 登录会话更新

默认会话 Cookie 改为 `GAME_CMS_SESSION`，避免与其他使用通用 JSESSIONID 的应用混淆。若外部 application.yml 已配置 `server.servlet.session.cookie.name`，请同步改成 `GAME_CMS_SESSION`。登录表单失效会返回登录页并显示重新登录提示，重新生成校验值；管理API仍保留CSRF校验。更新JAR并重启后重新打开登录页；保留原有数据库、密钥和端口配置。此改动处理会话隔离与失效恢复，不代表已经确认线上失败的全部原因。

## 图片按游戏保存（2026-11-08）

新图片存放为 `data/uploads/游戏ID/1.jpg`、`2.png`、`3.jpg` 等，每个游戏独立编号，保留真实格式。图标、横幅、截图、视频封面共用该游戏目录；同游戏重复图片复用已有文件，新增图片继续编号，调整前台展示顺序不会重命名文件或覆盖缓存中的图片。图片外链不自动下载。

升级前停止服务并备份整个data目录。首次启动会将数据库中实际存在的旧本地图片复制到对应游戏目录，并更新数据库引用；多个游戏共享旧图时，各自保存副本。原散列文件保留以兼容旧链接，不自动删除。迁移可重复运行，不重复产生图片或持续修改记录。新增上传与ZIP导入直接使用游戏目录。手工新建游戏使用自动生成ID，导入游戏使用来源game_id。只复制新目录而不带数据库不能完整迁移网站。

### 大型游戏目录与分页

首页每页展示 18 款已发布游戏，支持关键词搜索、分类和名称/更新时间排序；后台支持服务端分页、20/50/100 条每页、发布状态/分类筛选和跳页。数据库只读取当前页的游戏详情，避免浏览器一次加载全部记录。旧版 `/api/admin/games` 为兼容保留，管理页面使用 `/api/admin/games/page`。

升级启动会自动新增目录索引字段并回填旧记录，不需要手工修改游戏。更新前请备份 `data`，替换 JAR 后重启；保留原配置和数据目录。首页分页仍为服务端 HTML，分页有独立 canonical，筛选结果设为 noindex；每个游戏的独立 SEO 地址不变。动画遵循系统“减少动态效果”设置。

### 分类和首页推荐

- 游戏列表每行的「设置分类」可输入新分类或选择已有分类；保存后自动进入前台与后台筛选。编辑页也可修改分类。
- 点击「置顶推荐」将优先级设为 100，再点「取消置顶」恢复为 0。编辑页的「首页推荐优先级」支持 0–9999，越大越靠前；最高优先级的已发布游戏显示在首页首屏。相同优先级按更新时间排序。
- 首页默认「推荐优先」，访客也可选择最近更新或游戏名称排序；分类及搜索仍限制结果范围，草稿不会因置顶而公开。
- 网站地图 `/sitemap.xml` 实时读取数据库，不需要点击生成。站点允许索引且配置正式域名后，已发布且未勾选禁止索引的游戏自动加入；修改更新 lastmod，下线/删除自动移除。浏览器可通过 XSL 查看列表，搜索引擎仍读取标准 XML。
