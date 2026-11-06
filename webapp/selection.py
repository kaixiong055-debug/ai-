"""Validated product links and non-destructive imports into the existing collection queue."""
from __future__ import annotations
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from .store import Store


def page_link(url: str) -> tuple[str,str]:
    if len(url)>4096: raise ValueError('链接过长，请使用完整商品页链接而非分享文本')
    p=urlsplit(url.strip())
    host=p.hostname or ''
    if p.scheme not in ('https','http') or p.username or p.password or p.port not in (None,80,443):
        raise ValueError('仅支持淘宝、天猫、闲鱼的标准网页链接，不支持短链接或带账号信息的地址')
    platform='xianyu' if host in ('www.goofish.com','goofish.com') else 'taobao' if any(host==d or host.endswith('.'+d) for d in ('taobao.com','tmall.com')) else ''
    if not platform: raise ValueError('仅支持淘宝、天猫、闲鱼网页链接')
    return platform,urlunsplit(('https',host,p.path,p.query,''))


def product_link(url: str) -> dict:
    platform,clean=page_link(url)
    p=urlsplit(clean)
    valid=(platform=='xianyu' and p.path.rstrip('/')=='/item') or (p.hostname in ('item.taobao.com','detail.tmall.com') and p.path=='/item.htm')
    item_id=parse_qs(p.query).get('id',[''])[0]
    if not valid or not re.fullmatch(r'\d{1,30}',item_id): raise ValueError('不是有效商品链接，请复制带商品 ID 的完整商品页地址')
    return {'platform':platform,'item_id':item_id,'url':urlunsplit(('https',p.netloc,p.path,urlencode({'id':item_id}),''))}


def source_link(url: str) -> str:
    _,clean=page_link(url)
    p=urlsplit(clean)
    # Preserve only public entity/pagination selectors; discard tracking and session parameters.
    query={k:v[0] for k,v in parse_qs(p.query).items() if k in ('id','userId','user_id','shop_id','page','pageNo') and re.fullmatch(r'[\w-]{1,128}',v[0])}
    return urlunsplit(('https',p.netloc,p.path,urlencode(query),''))


def store_page(url: str) -> str:
    platform,clean=page_link(url)
    p=urlsplit(clean)
    if platform=='xianyu':
        if p.path.rstrip('/') not in ('/personal','/user') or not any(parse_qs(p.query).get(k) for k in ('userId','user_id')):
            raise ValueError('请先进入闲鱼卖家主页，再读取卖家商品')
    else:
        if p.hostname in ('item.taobao.com','detail.tmall.com','www.taobao.com','login.taobao.com') or not (p.path in ('','/','/search.htm','/category.htm','/shop/view_shop.htm') or p.path.startswith('/category-')):
            raise ValueError('请先进入淘宝/天猫店铺首页或店内商品列表页')
    return source_link(clean)


def import_links(store: Store, urls: list[str], keyword: str, candidates: list[dict] | None = None) -> list[int]:
    parsed=[product_link(url) for url in urls]  # Validate the whole input before writing.
    metadata={c.get('url'):c for c in (candidates or [])}
    ids=[]
    for product in parsed:
        with store.connect() as c:
            old=c.execute('SELECT * FROM products WHERE platform=? AND item_id=?',(product['platform'],product['item_id'])).fetchone()
        if old:
            pid=old['id']
            # Explicit re-import corrects the canonical source (e.g. Taobao -> Tmall), preserving collected fields.
            with store.connect() as c:c.execute('UPDATE products SET url=? WHERE id=?',(product['url'],pid))
        else:
            meta=metadata.get(product['url'],{})
            product.update(title=(meta.get('title') or f'待采集商品 {product["item_id"]}')[:200],
                           image_url=meta.get('image_url'),source_url=meta.get('source_url',''),source_name=meta.get('source_name',''))
            pid=store.upsert(product,keyword)
        if pid not in ids: ids.append(pid)
    return ids
