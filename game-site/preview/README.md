# 小小驯龙师：真实素材网页预览

使用提供的JSON清洗样例和原始ZIP素材制作，无后端、外部字体、框架或远程数据请求。站名“游选”是本次预览临时名称，不代表3387官方。

## 直接预览

Windows解压后双击 `打开预览.bat`，在浏览器中查看页面。也可尝试直接打开 `games/14545/index.html`；如果浏览器限制本地文件，使用启动脚本或下面的HTTP预览方式。`index.html` 是只有这一款游戏的简洁首页。图片、CSS、脚本和视频均在包内，联网仅用于点击后访问原始推广入口。

需要HTTP预览时，在这个文件夹运行：

```sh
python -m http.server 8080 --bind 127.0.0.1
```

访问 http://127.0.0.1:8080/games/14545/ 。

## 正式上线前必须生成域名配置

当前没有最终域名，因此预览页有 `noindex,follow`，robots禁止抓取，且不生成虚构的canonical和sitemap。不要将此默认预览直接部署并期待被收录。

在仓库根目录执行，域名替换为实际已配置的HTTPS域名：

```sh
python game-site/preview/build.py --site-url https://你的实际域名 --output /tmp/game-site-production
```

Windows示例：

```powershell
python game-site\preview\build.py --site-url https://你的实际域名 --output game-site\dist
```

命令只需配置一次域名，生成目录包含完整页面、图片、视频、可抓取的robots.txt、绝对canonical、分享元数据与sitemap.xml。将整个生成目录部署到静态网站托管服务根目录即可。此命令使用同目录的 `page-data.json`，预览包同时包含生成器和输入样例。

正式上线后还需检查HTTPS、返回200、搜索引擎抓取权限与站长平台提交情况。不能保证收录、排名或微信内推广链接不被限制。

## 本页实现

- 稳定游戏路径 `/games/14545/`，完整静态HTML，关闭JS仍有正文、图片与推广链接。
- 独立title/description、单个H1、H2层级、游戏版本和条件明确的福利说明。
- VideoGame/SoftwareApplication、WebPage、真实可见FAQ的JSON-LD；正式域名下含BreadcrumbList。
- 无虚构评分、下载量、价格、活动兑换码或iOS下载按钮。
- 真实素材、图像尺寸固定、非首屏图片懒加载，视频只在主动点击后加载。
- 普通链接为爬虫与无JS用户保留；图片放大、键盘切图、视频弹窗、滑动画廊。
- 微信内点击下载时提示系统浏览器操作，不自动下载、不静默跳转。
- 未使用3387后台Cookie、账号信息、佣金或临时素材签名。

## 本次范围

这是单款游戏的完整HTML视觉预览和域名SEO生成工具，尚不是任意原始JSON+ZIP批量导入器；Android状态依据当前样例，后续批量化仍需明确状态枚举。手机浏览器和微信内置浏览器模拟均需验证，真实微信、下载服务与真实搜索收录无法仅靠本地预览确认。
