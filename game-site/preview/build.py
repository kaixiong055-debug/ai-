"""Generate the real-material preview and deployment-specific SEO documents."""
from __future__ import annotations
import argparse
import html
import json
from pathlib import Path
import shutil
from string import Template
from urllib.parse import urlsplit

BASE=Path(__file__).resolve().parent
DATA=BASE/'page-data.json'
FAQ=[
 ('小小驯龙师是什么类型的游戏？','这是一款以恐龙收集、培养和阵容搭配为核心的回合挂机闯关游戏，包含PVE剧情副本、装备收集和跨服战斗等内容。介绍依据合作方提供的游戏素材整理。'),
 ('“首充送霸王龙”是登录就能领取吗？','不是。素材说明需要激活首充后领取专属霸王龙，属于有付费条件的活动。实际金额、领取方式及活动有效性以游戏内当期说明为准。'),
 ('这个页面提供什么版本？','本页展示安卓渠道版1.0.0的资料。iOS版本是否可用，请先通过游戏介绍页确认，本页不提供未经确认的iOS下载入口。'),
 ('在微信里能打开和下载吗？','页面可以作为普通网页阅读。微信内可能限制安装包下载或安装；遇到限制时，可在右上角菜单选择使用系统浏览器打开当前页，再查看对应下载入口。'),
 ('这里的截图和视频是本站实测吗？','不是。页面使用合作方提供的游戏宣传图、宣传视频及标注为试玩的视频素材，不代表本站独立游玩评测；游戏实际内容和活动以运营方说明为准。')
]

def site_url(value: str) -> str:
    parsed=urlsplit(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
        raise argparse.ArgumentTypeError('请填写网站的HTTPS根域名，例如 https://your-domain.cn，不含路径、凭据或查询参数')
    return value.rstrip('/')

def render(site: str, output: Path) -> None:
    data=json.loads(DATA.read_text(encoding='utf-8'))
    output.mkdir(parents=True,exist_ok=True)
    if output.resolve()!=BASE:
        shutil.copytree(BASE/'assets',output/'assets',dirs_exist_ok=True)
    game_path='/games/14545/'
    url=site+game_path if site else ''
    e=lambda value:html.escape(str(value),quote=True)
    gallery='\n'.join(f'<a class="gallery-item" data-lightbox data-caption="{e(item["label"])}" href="../../assets/14545/shot-{index:02d}.jpg" target="_blank" rel="noopener"><img src="../../assets/14545/shot-{index:02d}.jpg" width="608" height="1080" loading="lazy" decoding="async" alt="小小驯龙师游戏宣传画面：{e(item["label"])}"><span>{e(item["label"])} <span aria-hidden="true" style="display:inline">↗</span></span></a>' for index,item in enumerate(data['assets']['gallery'],1))
    faqs='\n'.join(f'<details><summary>{e(question)}</summary><p>{e(answer)}</p></details>' for question,answer in FAQ)
    application={'@type':['VideoGame','SoftwareApplication'],'name':data['name'],'description':data['intro'],'applicationCategory':'GameApplication','operatingSystem':'Android','softwareVersion':'1.0.0','inLanguage':'zh-CN','genre':['卡牌','放置','恐龙养成'],'installUrl':data['links']['download']}
    web_page={'@type':'WebPage','name':data['seo']['title'],'description':data['seo']['description'],'inLanguage':'zh-CN'}
    faq={'@type':'FAQPage','mainEntity':[{'@type':'Question','name':q,'acceptedAnswer':{'@type':'Answer','text':a}} for q,a in FAQ]}
    graph=[application,web_page,faq]
    if site:
        application.update({'@id':url+'#game','url':url,'image':site+'/assets/14545/hero.jpg'})
        web_page.update({'@id':url+'#webpage','url':url,'mainEntity':{'@id':url+'#game'}})
        faq['@id']=url+'#faq'
        graph.append({'@type':'BreadcrumbList','itemListElement':[{'@type':'ListItem','position':1,'name':'游戏发现','item':site+'/'},{'@type':'ListItem','position':2,'name':'小小驯龙师','item':url}]})
    structured=json.dumps({'@context':'https://schema.org','@graph':graph},ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    values={'title':e(data['seo']['title']+'｜游选'),'description':e(data['seo']['description']),'robots':'index,follow,max-image-preview:large' if site else 'noindex,follow','canonical':f'<link rel="canonical" href="{e(url)}">' if site else '', 'sharing':f'<meta property="og:url" content="{e(url)}">\n<meta property="og:image" content="{e(site)}/assets/14545/hero.jpg">\n<meta property="og:image:alt" content="小小驯龙师游戏宣传横幅">' if site else '', 'structured':structured,'gallery':gallery,'faq':faqs,'intro':e(data['intro']),'intro_url':e(data['links']['intro']),'download_url':e(data['links']['download'])}
    target=output/'games'/'14545';target.mkdir(parents=True,exist_ok=True)
    target.joinpath('index.html').write_text(Template((BASE/'templates'/'game.html').read_text(encoding='utf-8')).substitute(values),encoding='utf-8')
    home_canonical=f'<link rel="canonical" href="{e(site)}/">' if site else ''
    home=f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>游选｜发现下一款想玩的游戏</title><meta name="description" content="查看小小驯龙师的游戏介绍、宣传画面、版本与安卓渠道下载入口。"><meta name="robots" content="{values['robots']}">{home_canonical}<link rel="icon" href="assets/14545/icon.jpg"><link rel="stylesheet" href="assets/site.css"></head><body><header class="site-header"><div class="container header-inner"><a class="brand" href="index.html"><span class="brand-mark">游</span>游选<span class="brand-en">PLAY SOMETHING GOOD</span></a><a class="header-download" href="games/14545/index.html">探索游戏 →</a></div></header><main class="container"><section class="home-hero"><span class="eyebrow">FIND YOUR NEXT ADVENTURE</span><h1>下一次冒险，<br>从喜欢的游戏开始。</h1><p>先看游戏画面与玩法，再选择是否下载。</p></section><article class="home-card"><img src="assets/14545/hero.jpg" width="1008" height="567" alt="小小驯龙师驯龙之旅游戏宣传横幅"><div><div class="tags"><span>恐龙收集</span><span>卡牌养成</span><span>竖版放置</span></div><h2>小小驯龙师</h2><p>收集远古恐龙，搭配你的专属阵容。从一次孵化开始，开启回合挂机闯关之旅。</p><a class="button primary" href="games/14545/index.html">了解这款游戏 →</a></div></article></main><footer class="footer container"><p>游选 · 游戏推广介绍站 · 含推广链接，非游戏官方。</p></footer></body></html>'''
    (output/'index.html').write_text(home,encoding='utf-8')
    if site:
        (output/'robots.txt').write_text('User-agent: *\nAllow: /\nSitemap: '+site+'/sitemap.xml\n',encoding='utf-8')
        (output/'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>'+html.escape(site+'/')+'</loc></url><url><loc>'+html.escape(url)+'</loc></url></urlset>\n',encoding='utf-8')
    else:
        (output/'robots.txt').write_text('User-agent: *\nDisallow: /\n',encoding='utf-8')
        (output/'sitemap.xml').unlink(missing_ok=True)
    print(json.dumps({'output':str(output),'mode':'production' if site else 'preview-noindex','canonical':url or None,'game_pages':1},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site-url',type=site_url,default=None)
    parser.add_argument('--output',type=Path,default=BASE)
    args=parser.parse_args();render(args.site_url or '',args.output)
