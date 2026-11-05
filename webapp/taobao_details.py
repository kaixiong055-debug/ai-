"""Taobao detail adapter: ordinary browser responses, no synthesized API signatures."""
from __future__ import annotations
import json
import time
from html.parser import HTMLParser
from urllib.parse import parse_qs, quote, urlsplit
from playwright.sync_api import Error as BrowserError
from .details import normalize


class Description(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[str]=[]
        self.text: list[str]=[]
        self.skip=0
    def handle_starttag(self, tag: str, attrs: list[tuple[str,str | None]]) -> None:
        if tag in ('script','style'): self.skip+=1
        if tag=='img' and not self.skip:
            values=dict(attrs)
            value=values.get('data-src') or values.get('src')
            if value:
                value=normalize(value)
                if urlsplit(value).scheme=='https' and value not in self.images: self.images.append(value)
    def handle_endtag(self, tag: str) -> None:
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
    def handle_data(self, data: str) -> None:
        if not self.skip and data.strip(): self.text.append(data.strip())


def description_fields(data: dict) -> tuple[list[str], str]:
    content=data.get('pcDescContent') or data.get('desc') or data.get('description') or ''
    if isinstance(content,dict): content=content.get('content') or ''
    if not isinstance(content,str): return [],''
    parser=Description(); parser.feed(content)
    return parser.images,'\n'.join(parser.text)


def parse_detail(payload: dict, item_id: str, request_id: str = '') -> dict | None:
    data=payload.get('data')
    if not isinstance(data,dict): return None
    item=data.get('item')
    if not isinstance(item,dict): return None
    actual=str(item.get('itemId') or item.get('id') or request_id)
    if actual!=item_id: return None
    kinds: dict[str,str]={}
    def add(value: object, kind: str) -> None:
        if isinstance(value,dict): value=value.get('url') or value.get('image')
        if isinstance(value,str) and value:
            value=normalize(value)
            if urlsplit(value).scheme=='https': kinds.setdefault(value,kind)
    for image in item.get('images',[]) if isinstance(item.get('images'),list) else []: add(image,'gallery')
    sku=data.get('skuBase') or {}
    if isinstance(sku,dict):
        for prop in sku.get('props',[]) if isinstance(sku.get('props'),list) else []:
            if not isinstance(prop,dict): continue
            for value in prop.get('values',[]) if isinstance(prop.get('values'),list) else []:
                if isinstance(value,dict): add(value.get('image'),'sku')
    images,text=description_fields(data)
    if not images and not text: images,text=description_fields(item)
    for image in images: add(image,'detail')
    if not kinds: return None
    return {'gallery':list(kinds),'image_kinds':kinds,'description':text,
            'detail_status':'collected' if images else 'partial',
            'detail_error':None if images else '已取得轮播/SKU 图片，但尚未取得详情长图；可补采重试'}


def merge_result(found: dict, incoming: dict) -> None:
    found['gallery']=list(dict.fromkeys(found.get('gallery',[])+incoming['gallery']))
    kinds=found.setdefault('image_kinds',{})
    for url,kind in incoming['image_kinds'].items():
        if url not in kinds or kinds[url]=='gallery': kinds[url]=kind
    if incoming.get('description') or 'description' not in found:
        found['description']=incoming.get('description','')
    complete=any(kind=='detail' for kind in kinds.values())
    found['detail_status']='collected' if complete else 'partial'
    found['detail_error']=None if complete else incoming.get('detail_error')


def request_item(url: str) -> str:
    try:
        raw=parse_qs(urlsplit(url).query).get('data',['{}'])[0]
        data=json.loads(raw)
        return str(data.get('id') or data.get('itemId') or '') if isinstance(data,dict) else ''
    except (ValueError,TypeError): return ''


def collect(context: object, item_id: str) -> dict:
    page=context.new_page()
    found: dict={}
    desc_images: list[str]=[]
    desc_text=''
    restricted=False
    description_response=False
    def response_handler(response: object) -> None:
        nonlocal restricted, desc_text, description_response
        parsed=urlsplit(response.url)
        host=parsed.hostname or ''
        if not (host=='taobao.com' or host.endswith('.taobao.com') or host=='tmall.com' or host.endswith('.tmall.com')): return
        path=parsed.path.lower()
        main=any('/'+api+'/' in path for api in ('mtop.taobao.pcdetail.data.get','mtop.taobao.detail.get','mtop.taobao.detail.data.get'))
        desc='/mtop.taobao.detail.getdesc/' in path
        if not main and not desc: return
        bound=request_item(response.url)
        if bound and bound!=item_id: return
        try:
            payload=response.json()
            if not isinstance(payload,dict): return
            ret=str(payload.get('ret',[]))
            if any(x in ret for x in ('FAIL_SYS_USER_VALIDATE','FAIL_SYS_SESSION_EXPIRED','RGV587','FAIL_SYS_LOGIN')): restricted=True
            if main:
                result=parse_detail(payload,item_id,bound)
                if result: merge_result(found,result)
            elif bound==item_id and isinstance(payload.get('data'),dict):
                urls,text=description_fields(payload['data']);desc_images.extend(urls)
                if urls: description_response=True
                if text: desc_text=text
        except (ValueError,TypeError,BrowserError): return
    page.on('response',response_handler)
    try:
        page.goto('https://item.taobao.com/item.htm?id='+quote(item_id,safe=''),wait_until='domcontentloaded',timeout=30000)
        deadline=time.monotonic()+25
        while time.monotonic()<deadline and not found and not restricted:
            if 'login' in (urlsplit(page.url).hostname or ''): restricted=True;break
            page.wait_for_timeout(500)
        if found:
            # Only inspect known description containers after the item's identity was verified.
            # Bounded lazy-load observation. DOM stability is not proof that all images exist.
            stable=0
            previous=()
            for _ in range(12):
                container=page.locator('#description, #J_DivItemDesc, [data-testid="item-description"]').first
                if container.count():
                    container.scroll_into_view_if_needed(timeout=5000)
                    parser=Description();parser.feed(container.inner_html(timeout=5000))
                    desc_images.extend(parser.images)
                    if parser.text: desc_text='\n'.join(parser.text)
                page.mouse.wheel(0,1000)
                page.wait_for_timeout(1000)
                snapshot=tuple(dict.fromkeys(desc_images))
                stable=stable+1 if snapshot==previous else 0
                previous=snapshot
                response_complete=description_response or any(k=='detail' for k in found['image_kinds'].values())
                if response_complete and stable>=2: break
            for image in desc_images:
                if image not in found['gallery']: found['gallery'].append(image)
                found['image_kinds'].setdefault(image,'detail')
            if desc_text: found['description']=desc_text
            if description_response or (found.get('detail_status')=='collected'):
                found.update(detail_status='collected',detail_error=None)
            elif desc_images:
                found.update(detail_status='partial',detail_error='已保存可见详情图，未取得完整描述响应，无法确认图集完整；可补采重试')
            return found
        return {'detail_status':'failed','detail_error':'淘宝详情需要登录或人工验证，请完成登录后重试' if restricted else '未取得匹配商品的淘宝详情：可能访问受限、商品下架或接口结构变化；保留已有主图'}
    except BrowserError:
        if found:
            found.update(detail_status='partial',detail_error='已保留获取的图片；详情页面加载中断，请补采重试')
            return found
        return {'detail_status':'failed','detail_error':'淘宝详情页面加载失败或窗口被关闭，请检查网络后重试'}
    finally:
        if not page.is_closed():
            try: page.close()
            except BrowserError: restricted=True
