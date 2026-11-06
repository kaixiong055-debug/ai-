"""Collect a matching Xianyu item's actual gallery from its detail response.

No signed API synthesis: the logged-in browser performs ordinary page navigation.
Unknown response shapes are reported, never replaced by recommendation images.
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlsplit
from playwright.sync_api import sync_playwright, Error as BrowserError

ROOT = Path(__file__).resolve().parent.parent


def normalize(url: str) -> str:
    if url.startswith('//'): return 'https:' + url
    if url.startswith('http://'): return 'https://' + url[7:]
    return url


def parse_detail(payload: dict, item_id: str) -> dict | None:
    data = payload.get('data')
    if not isinstance(data,dict): return None
    item = data.get('itemDO') or data.get('item')
    if not isinstance(item,dict) or str(item.get('itemId',item.get('id',''))) != item_id:
        return None
    infos = item.get('imageInfos') or item.get('images')
    if not isinstance(infos,list): return None
    urls=[]
    for info in infos:
        value = (info.get('url') or info.get('imageUrl')) if isinstance(info,dict) else info
        if isinstance(value,str) and value:
            value=normalize(value)
            if value not in urls and urlsplit(value).scheme=='https': urls.append(value)
    if not urls: return None
    return {**({'title':str(item['title'])[:200]} if item.get('title') else {}),'gallery':urls,'description':str(item.get('desc') or item.get('description') or ''),
            'detail_status':'collected','detail_error':None}


def collect(context: object, item_id: str) -> dict:
    page=context.new_page()
    found: dict = {}
    restricted=False
    def response_handler(response: object) -> None:
        nonlocal restricted
        parsed=urlsplit(response.url)
        if parsed.hostname not in ('h5api.m.goofish.com','h5api.m.taobao.com') or 'mtop.taobao.idle.pc.detail' not in parsed.path.lower():
            return
        try:
            payload=response.json()
            if not isinstance(payload,dict): return
            ret=str(payload.get('ret',[]))
            if any(x in ret for x in ('FAIL_SYS_USER_VALIDATE','FAIL_SYS_SESSION_EXPIRED','RGV587','FAIL_SYS_LOGIN')):
                restricted=True
            result=parse_detail(payload,item_id)
            if result: found.update(result)
        except (ValueError,BrowserError):
            return
    page.on('response',response_handler)
    try:
        page.goto('https://www.goofish.com/item?id='+quote(item_id,safe=''),wait_until='domcontentloaded',timeout=30000)
        deadline=time.monotonic()+25
        while time.monotonic()<deadline and not found and not restricted:
            if 'login' in page.url.lower(): restricted=True; break
            page.wait_for_timeout(500)
        if found: return found
        return {'detail_status':'failed','detail_error':
                '详情需要登录或人工验证，请在平台账号重新登录后重试' if restricted else
                '未获取到匹配商品的图集：可能访问受限、商品下架或详情接口结构变化；保留已有主图'}
    except BrowserError:
        return {'detail_status':'failed','detail_error':'详情页面加载失败或窗口被关闭，请检查网络后重试'}
    finally:
        if not page.is_closed():
            try: page.close()
            except BrowserError: restricted=True


def enrich(products: list[dict], progress: object = None, platform: str = 'xianyu') -> None:
    if platform not in ('taobao','xianyu'): raise ValueError('不支持的详情平台')
    collector=collect
    if platform=='taobao':
        from .taobao_details import collect as collector
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            context=browser.new_context(storage_state=str(ROOT/'state'/f'{platform}_state.json'),locale='zh-CN')
            for idx, product in enumerate(products):
                if idx: time.sleep(4.5)
                product.update(collector(context,str(product['item_id'])))
                if progress: progress(idx+1,product)
        finally:
            browser.close()


def main() -> int:
    item_id, output = sys.argv[1:3]
    platform=sys.argv[3] if len(sys.argv)>3 else 'xianyu'
    product={'item_id':item_id}
    try: enrich([product],platform=platform)
    except (BrowserError,OSError,ValueError):
        product.update(detail_status='failed',detail_error='详情浏览器启动失败，请检查登录状态和浏览器安装')
    Path(output).write_text(json.dumps(product,ensure_ascii=False),encoding='utf-8')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
