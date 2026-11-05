"""Single persistent Playwright subprocess, controlled through private local command files."""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright, Error as BrowserError
from .selection import page_link, product_link, source_link, store_page

ROOT=Path(__file__).resolve().parent.parent


def write_json(path: Path, data: dict) -> None:
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    temporary.replace(path)


def save_login(context: object, platform: str, root: Path = ROOT) -> bool:
    domains=('taobao.com','tmall.com') if platform=='taobao' else ('goofish.com','taobao.com')
    valid=False
    for cookie in context.cookies():
        domain=cookie.get('domain','').lstrip('.')
        if (cookie.get('name') in ('unb','tracknick','_nk_') and cookie.get('value') not in (None,'','0','null','undefined')
            and any(domain==d or domain.endswith('.'+d) for d in domains)
            and (cookie.get('expires',-1)==-1 or cookie.get('expires',0)>time.time())):
            valid=True;break
    if not valid: return False
    state=root/'state';state.mkdir(exist_ok=True)
    target=state/f'{platform}_state.json'
    temporary=state/f'{platform}_picker.tmp'
    try:
        context.storage_state(path=str(temporary))
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return True


def extract_candidates(page: object, platform: str, source: str, name: str, limit: int) -> list[dict]:
    # Only product hyperlinks are candidates. Ownership is not inferred from page proximity.
    raw=page.locator('a[href]').evaluate_all('''nodes => nodes.slice(0,6000).map(a=>({
      url:a.href,title:(a.getAttribute('title')||a.innerText||a.querySelector('img')?.alt||'').trim().slice(0,200),
      image_url:a.querySelector('img')?.currentSrc||a.querySelector('img')?.src||null
    }))''')
    seen=set();result=[]
    for row in raw:
        try: p=product_link(row['url'])
        except (ValueError,TypeError): continue
        if p['platform']!=platform or p['item_id'] in seen: continue
        seen.add(p['item_id'])
        p.update(title=row['title'] or f'商品 {p["item_id"]}',image_url=row['image_url'],source_url=source,source_name=name,
                 ownership='来源页面候选，店铺归属未验证，请人工核对')
        result.append(p)
        if len(result)>=limit: break
    return result


def discover(page: object, platform: str, rounds: int, limit: int, publish: object) -> list[dict]:
    source=store_page(page.url)
    name=page.title()[:200]
    found={}
    for index in range(rounds):
        if source_link(page.url)!=source:
            raise ValueError('页面已离开原店铺，请重新读取当前页面')
        for candidate in extract_candidates(page,platform,source,name,limit): found[candidate['url']]=candidate
        publish(list(found.values())[:limit],index+1)
        if len(found)>=limit: break
        # Scroll incrementally, retaining earlier lazy-loaded cards.
        for _ in range(3):
            page.mouse.wheel(0,900);page.wait_for_timeout(700)
            if source_link(page.url)!=source:
                publish(list(found.values())[:limit],index+1)
                raise ValueError('读取时页面发生切换，已保留原页面候选，请重新读取')
            for candidate in extract_candidates(page,platform,source,name,limit): found[candidate['url']]=candidate
            publish(list(found.values())[:limit],index+1)
            if len(found)>=limit: break
        if len(found)>=limit: break
        if index+1<rounds:
            next_page=page.get_by_role('button',name='下一页',exact=True)
            if next_page.count()!=1:
                next_page=page.get_by_role('link',name='下一页',exact=True)
            if next_page.count()==1 and next_page.is_enabled():
                next_page.click(timeout=5000);page.wait_for_timeout(2000)
                current=source_link(page.url)
                # Same shop host/path is required after a pagination action.
                from urllib.parse import urlsplit, parse_qs
                old,new=urlsplit(source),urlsplit(current)
                identity=lambda u:{k:v for k,v in parse_qs(u.query).items() if k not in ('page','pageNo')}
                if (old.netloc,old.path,identity(old))!=(new.netloc,new.path,identity(new)):
                    raise ValueError('翻页离开原店铺，已停止；请在浏览器手动翻页后重新读取')
                source=current
            else:
                page.wait_for_timeout(1500)
    publish(list(found.values())[:limit],min(rounds,index+1))
    return list(found.values())[:limit]


def main() -> int:
    folder=Path(sys.argv[1]);platform=sys.argv[2]
    state={'status':'starting','message':'正在打开平台浏览器','candidates':[],'pages':[]}
    status=folder/'status.json'
    write_json(status,state)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=False)
            kwargs={'locale':'zh-CN'}
            login=ROOT/'state'/f'{platform}_state.json'
            if login.exists(): kwargs['storage_state']=str(login)
            context=browser.new_context(**kwargs)
            page=context.new_page()
            page.goto('https://www.goofish.com/' if platform=='xianyu' else 'https://www.taobao.com/',wait_until='domcontentloaded',timeout=30000)
            state.update(status='ready',message='请在平台窗口浏览商品或店铺，再回管理页面读取；可选择标签页')
            last='';pages={};tick=0
            while browser.is_connected() and context.pages:
                if tick%4==0:
                    for tab in context.pages:
                        if not tab.is_closed() and tab not in pages.values():
                            pages[str(max([int(k) for k in pages] or [-1])+1)]=tab
                    pages={key:tab for key,tab in pages.items() if not tab.is_closed()}
                    summaries=[]
                    for key,tab in pages.items():
                        try:
                            pf,_=page_link(tab.url)
                            if pf==platform: summaries.append({'id':key,'title':tab.title()[:150],'url':source_link(tab.url)})
                        except (ValueError,BrowserError): continue
                    state['pages']=summaries
                    write_json(status,state)
                command=folder/'command.json'
                if command.exists():
                    cmd=json.loads(command.read_text(encoding='utf-8'))
                    if cmd['id']!=last:
                        last=cmd['id'];state['command_id']=last
                        try:
                            page=pages.get(cmd.get('page',''),page)
                            if page.is_closed(): raise ValueError('标签页已关闭，请选择其他标签页')
                            state.update(status='busy',message='正在读取平台页面')
                            write_json(status,state)
                            if cmd['action']=='save_login':
                                saved=save_login(context,platform)
                                state.update(status='ready',message='已保存本窗口登录状态，平台有效性待采集验证' if saved else '未检测到有效登录标记，请先在平台窗口完成登录')
                                write_json(status,state)
                                continue
                            if cmd['action']=='navigate':
                                pf,url=page_link(cmd['url'])
                                if pf!=platform: raise ValueError('链接平台与当前浏览器不一致')
                                page.goto(url,wait_until='domcontentloaded',timeout=30000)
                                result=[]
                            elif cmd['action']=='current':
                                product=product_link(page.url)
                                if product['platform']!=platform: raise ValueError('当前商品平台不匹配')
                                product.update(title=page.title()[:200],source_url=product['url'],source_name='浏览器选品')
                                result=[product]
                            else:
                                if page_link(page.url)[0]!=platform: raise ValueError('当前页面平台不匹配')
                                def progress(items: list[dict], rounds: int) -> None:
                                    state.update(candidates=items,message=f'已读取 {rounds} 轮，发现 {len(items)} 个候选商品（请核对归属）')
                                    write_json(status,state)
                                if cmd['action']=='shop':
                                    result=discover(page,platform,cmd['rounds'],cmd['limit'],progress)
                                else:
                                    result=extract_candidates(page,platform,source_link(page.url),page.title()[:200],cmd['limit'])
                            if cmd['action']!='navigate':
                                try: save_login(context,platform)
                                except (OSError,BrowserError):
                                    state.update(status='ready',candidates=result,message='候选已读取，但登录状态保存失败；请检查文件权限或在平台账号重新登录')
                                    write_json(status,state);continue
                            state.update(status='ready',candidates=result,message=f'读取完成：{len(result)} 个候选商品。请勾选后加入商品库；未自动采集详情或下载图片。')
                        except (ValueError,BrowserError):
                            state.update(status='ready',message='读取失败：请确认标签页是商品/店铺页并完成登录验证；可手动翻页后读取当前页。已发现候选保留。')
                        write_json(status,state)
                time.sleep(.25);tick+=1
                # Pump Playwright events without exposing any page content outside the candidate schema.
                if not page.is_closed(): page.wait_for_timeout(10)
            browser.close()
    except (BrowserError,OSError,ValueError):
        state.update(status='failed',message='选品浏览器启动或访问失败，请检查 Chromium、平台登录和网络；可关闭后重新打开')
        write_json(status,state)
        return 1
    state.update(status='closed',message='选品浏览器已关闭，已读取候选仍可加入商品库')
    write_json(status,state)
    return 0

if __name__=='__main__': raise SystemExit(main())
