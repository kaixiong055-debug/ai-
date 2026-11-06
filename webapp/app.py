"""Loopback-only management API; private files are never mounted."""
from __future__ import annotations
import http.client
import csv
import json
import io
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware
from PIL import Image
from . import images
from .exporter import write_archive
from .store import Store
from .tasks import TaskManager, ROOT
from .publishers import Draft, PUBLISHERS
from .login_worker import MESSAGES
from .selection import import_links, page_link
from .picker_session import PickerSession

class Selection(BaseModel):
    ids: list[int] = Field(min_length=1,max_length=1000)

class DetailSelection(Selection):
    mode: Literal['background','compatible'] = 'background'


class Search(BaseModel):
    keywords: list[str] = Field(min_length=1,max_length=20)
    platforms: list[str] = Field(min_length=1,max_length=2)
    pages: int = Field(1,ge=1,le=20)


class LinkImport(BaseModel):
    urls: list[str] = Field(min_length=1,max_length=200)
    keyword: str = Field('链接选品',min_length=1,max_length=100)

class BrowserStart(BaseModel):
    platform: Literal['taobao','xianyu']

class OriginalProduct(BaseModel):
    url: str = Field(...,max_length=2048)


class BrowserCommand(BaseModel):
    action: Literal['navigate','current','list','shop','save_login']
    page: str = Field('',max_length=30)
    url: str = Field('',max_length=2048)
    rounds: int = Field(3,ge=1,le=10)
    limit: int = Field(100,ge=1,le=200)


def csv_data(rows: list[dict]) -> bytes:
    stream=io.StringIO(newline='')
    fields=['platform','item_id','title','current_price','url','keyword','crawled_at','image_status','image_path','image_error']
    writer=csv.writer(stream); writer.writerow(fields)
    for row in rows:
        values=[]
        for k in fields:
            v=str(row.get(k) if row.get(k) is not None else '')
            values.append("'"+v if v.lstrip().startswith(('=','+','-','@','\t','\r')) else v)
        writer.writerow(values)
    return stream.getvalue().encode('utf-8-sig')


def create_app(data_dir: Path | None = None) -> FastAPI:
    store=Store(data_dir or Path(os.environ.get('PRODUCT_TOOL_DATA',ROOT/'data'/'webapp')))
    tasks=TaskManager(store)
    picker=PickerSession(store.root)
    tasks.picker=picker
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        tasks.close()
        picker.close()
    app=FastAPI(title='商品采集管理',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.store=store; app.state.tasks=tasks; app.state.picker=picker
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost'])
    @app.middleware('http')
    async def local_guard(request: Request, call_next):
        if request.method not in ('GET','HEAD'):
            origin=request.headers.get('origin')
            if (origin and origin != str(request.base_url).rstrip('/')) or request.headers.get('X-Local-Tool')!='1':
                return Response('禁止跨站操作',status_code=403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        return response
    @app.get('/')
    def index() -> FileResponse:
        return FileResponse(Path(__file__).parent/'static'/'index.html')
    app.mount('/static',StaticFiles(directory=Path(__file__).parent/'static'),name='static')
    @app.get('/favicon.ico')
    def favicon() -> Response:
        return Response(status_code=204)
    @app.get('/api/health')
    def health() -> dict:
        return {'app':'product-crawling-local','status':'ok'}
    @app.post('/api/selection/links')
    def add_links(body: LinkImport) -> dict:
        try: return {'ids':import_links(store,body.urls,body.keyword),'message':'已加入商品库，尚未采集详情或下载图片'}
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    @app.post('/api/selection/browser/product')
    def open_original(body: OriginalProduct) -> dict:
        with tasks.lock:
            if tasks.thread and tasks.thread.is_alive():
                raise HTTPException(409,'采集期间请先查看本地详情；完成或停止任务后可在登录窗口打开原商品')
            if any(proc.poll() is None for proc in tasks.logins.values()):
                raise HTTPException(409,'请先完成登录窗口操作')
            try:return picker.open_product(body.url)
            except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    @app.get('/api/selection/browser')
    def browser_status() -> dict:
        state = picker.status()
        with tasks.lock:
            active = tasks.active
            item_states = dict(active.get('item_states', {})) if active.get('kind') == 'details' and active.get('status') in ('running', 'stopping') else {}
        candidates = []
        with store.connect() as connection:
            for candidate in state.get('candidates', []):
                card = dict(candidate)
                product = connection.execute('SELECT id,detail_status,detail_error FROM products WHERE platform=? AND item_id=?',
                                             (card['platform'], str(card['item_id']))).fetchone()
                card.update(product_id=None, collection_status='not_imported', collection_error=None)
                if product:
                    card.update(product_id=product['id'], collection_status=item_states.get(str(product['id']), product['detail_status']),
                                collection_error=product['detail_error'])
                    if card['collection_status'] in ('queued', 'running'): card['collection_error'] = None
                candidates.append(card)
        return {**state, 'candidates': candidates}
    @app.post('/api/selection/browser/open')
    def browser_open(body: BrowserStart) -> dict:
        if any(proc.poll() is None for proc in tasks.logins.values()):raise HTTPException(409,'请先完成登录窗口操作')
        if tasks.thread and tasks.thread.is_alive():raise HTTPException(409,'请先完成或停止采集任务')
        try: return picker.start(body.platform)
        except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    @app.post('/api/selection/browser/command')
    def browser_command(body: BrowserCommand) -> dict:
        try:
            if body.action=='navigate': page_link(body.url)
            return picker.send(body.model_dump())
        except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    @app.post('/api/selection/browser/close')
    def browser_close() -> dict:
        if picker.leased:raise HTTPException(409,'窗口正在采集详情，请先停止任务')
        picker.close();return picker.status()
    @app.get('/api/selection/browser/preview')
    def candidate_preview(url: str) -> Response:
        candidate=next((c for c in picker.status()['candidates'] if c['url']==url),None)
        if not candidate or not candidate.get('image_url'): raise HTTPException(404,'候选无预览图')
        try:
            data=images.fetch_image(candidate['image_url']);images.verify_image(data)
            with Image.open(io.BytesIO(data)) as img:
                img.thumbnail((300,300));out=io.BytesIO();img.convert('RGB').save(out,format='JPEG',quality=80)
            return Response(out.getvalue(),media_type='image/jpeg',headers={'Cache-Control':'private, max-age=300'})
        except (ValueError,OSError,http.client.HTTPException) as exc:
            raise HTTPException(502,'候选预览不可用，仍可采集商品详情') from exc
    @app.post('/api/selection/browser/import')
    def browser_import(body: LinkImport) -> dict:
        candidates=picker.status()['candidates']
        allowed={c['url'] for c in candidates}
        if any(url not in allowed for url in body.urls): raise HTTPException(422,'候选已更新，请刷新列表重新选择')
        try: return {'ids':import_links(store,body.urls,body.keyword,candidates),'message':'已加入商品库；请勾选商品后采集详情，图片需单独下载'}
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc
    @app.get('/api/products')
    def products(q: str='',platform: str='',status: str='',page: int=Query(1,ge=1),size: int=Query(24,ge=1,le=100)) -> dict:
        return store.products(q,platform,status,page,size)
    @app.get('/api/products/{pid}')
    def detail(pid: int) -> dict:
        rows=store.selected([pid])
        if not rows: raise HTTPException(404,'商品不存在')
        return {**rows[0],'gallery':store.gallery(pid)}
    @app.get('/api/images/{pid}/preview')
    def preview(pid: int) -> Response:
        rows=store.selected([pid])
        if not rows or not rows[0].get('image_url'): raise HTTPException(404,'没有主图地址')
        try:
            data=images.fetch_image(rows[0]['image_url'])
            images.verify_image(data)
            with Image.open(io.BytesIO(data)) as img:
                img.thumbnail((480,480))
                out=io.BytesIO()
                img.convert('RGB').save(out,format='JPEG',quality=80)
            return Response(out.getvalue(),media_type='image/jpeg',headers={'Cache-Control':'private, max-age=300'})
        except (ValueError,OSError,http.client.HTTPException) as exc:
            raise HTTPException(502,'预览暂不可用，可选择下载重试查看原因') from exc
    @app.post('/api/details/collect')
    def collect_details(selection: DetailSelection) -> dict:
        try: return tasks.start('details',selection.model_dump())
        except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    @app.post('/api/gallery/download')
    def download_gallery(selection: Selection) -> dict:
        with store.connect() as c:
            rows=c.execute('SELECT DISTINCT product_id FROM product_images WHERE id IN ('+','.join('?' for _ in selection.ids)+')',selection.ids).fetchall()
        if not rows: raise HTTPException(404,'图片不存在')
        try: return tasks.start('images',{'ids':[r[0] for r in rows],'image_ids':selection.ids})
        except ValueError as exc: raise HTTPException(409,str(exc)) from exc
    @app.get('/api/gallery/{iid}')
    def gallery_image(iid: int, preview: bool = False) -> Response:
        with store.connect() as c:
            row=c.execute('SELECT * FROM product_images WHERE id=?',(iid,)).fetchone()
        if not row: raise HTTPException(404,'图片不存在')
        if row['path']:
            path=(store.root/row['path']).resolve()
            if path.is_relative_to(store.root/'images') and path.is_file(): return FileResponse(path)
        if not preview: raise HTTPException(404,'图片尚未下载')
        try:
            data=images.fetch_image(row['url']); images.verify_image(data)
            with Image.open(io.BytesIO(data)) as img:
                img.thumbnail((480,480)); out=io.BytesIO(); img.convert('RGB').save(out,format='JPEG',quality=80)
            return Response(out.getvalue(),media_type='image/jpeg',headers={'Cache-Control':'private, max-age=300'})
        except (ValueError,OSError,http.client.HTTPException) as exc:
            raise HTTPException(502,'图片预览失败，请下载重试') from exc
    @app.post('/api/products/delete')
    def delete(selection: Selection) -> dict:
        store.delete(selection.ids); return {'ok':True}
    @app.get('/api/images/{pid}')
    def image(pid: int) -> FileResponse:
        rows=store.selected([pid])
        path=(store.root/(rows[0].get('image_path') or 'missing')).resolve() if rows else store.root/'missing'
        if not path.is_relative_to(store.root/'images') or not path.is_file(): raise HTTPException(404,'主图尚未下载')
        return FileResponse(path)
    @app.post('/api/images/download')
    def download(selection: Selection) -> dict:
        try: return tasks.start('images',selection.model_dump())
        except ValueError as e: raise HTTPException(409,str(e)) from e
    @app.post('/api/tasks')
    def start(search: Search) -> dict:
        data=search.model_dump()
        data['keywords']=list(dict.fromkeys(k.strip() for k in data['keywords'] if k.strip()))
        if not data['keywords'] or any(len(k)>100 for k in data['keywords']) or any(p not in ('taobao','xianyu') for p in data['platforms']):
            raise HTTPException(422,'关键词或平台参数无效')
        data['platforms']=list(dict.fromkeys(data['platforms']))
        try: return tasks.start('crawl',data)
        except ValueError as e: raise HTTPException(409,str(e)) from e
    @app.get('/api/tasks')
    def history() -> list[dict]: return store.tasks()
    @app.post('/api/tasks/stop')
    def stop() -> dict:
        tasks.stop(); return {'ok':True}
    @app.get('/api/accounts')
    def accounts() -> list[dict]:
        result=[]
        for platform in ('taobao','xianyu'):
            proc=tasks.logins.get(platform)
            status='已保存本地状态，平台有效性待采集验证' if (ROOT/'state'/f'{platform}_state.json').exists() else '未登录'
            if proc:
                code=proc.poll()
                if code is None: status='登录窗口运行中，请手动扫码或验证'
                else:
                    report=tasks.login_reports.get(platform)
                    try:
                        outcome=json.loads(report.read_text(encoding='utf-8')).get('code') if report else None
                    except (OSError,ValueError):
                        outcome=None
                    status=MESSAGES.get(outcome,'登录进程未返回诊断结果，请更新工具后重新打开登录窗口')
            result.append({'platform':platform,'status':status})
        return result
    @app.post('/api/accounts/{platform}/login')
    def login(platform: str) -> dict:
        if platform not in ('taobao','xianyu'): raise HTTPException(404)
        try:
            if picker.proc and picker.proc.poll() is None:
                if tasks.thread and tasks.thread.is_alive():raise ValueError('请先完成或停止采集任务')
                if picker.platform!=platform:raise ValueError('请先关闭其他平台选品窗口，再登录此平台')
                picker.send({'action':'navigate','url':'https://www.taobao.com/' if platform=='taobao' else 'https://www.goofish.com/'})
            else:tasks.login(platform)
        except ValueError as e: raise HTTPException(409,str(e)) from e
        return {'message':'已请求打开本机登录窗口'}
    @app.post('/api/export/{kind}')
    def export(kind: str,selection: Selection) -> Response:
        rows=store.selected(selection.ids)
        if kind=='csv': return Response(csv_data(rows),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=products.csv'})
        if kind!='zip': raise HTTPException(404)
        export_dir = store.root / 'exports'
        export_dir.mkdir(exist_ok=True)
        fd, filename = tempfile.mkstemp(suffix='.zip',dir=export_dir)
        os.close(fd)
        archive = Path(filename)
        try:
            write_archive(archive,store,rows)
        except Exception:
            archive.unlink(missing_ok=True)
            raise
        return FileResponse(archive,media_type='application/zip',filename='products.zip',background=BackgroundTask(archive.unlink,missing_ok=True))
    @app.get('/api/drafts')
    def drafts() -> list[dict]: return store.drafts()
    @app.post('/api/drafts')
    def add_drafts(selection: Selection) -> dict:
        store.add_drafts(selection.ids); return {'ok':True}
    @app.put('/api/drafts/{did}')
    def edit_draft(did: int,draft: Draft) -> dict:
        if not store.update_draft(did,draft.model_dump()): raise HTTPException(404)
        return {'ok':True}
    @app.get('/api/publishers')
    def publishers() -> list[dict]: return [p.info() for p in PUBLISHERS.values()]
    @app.post('/api/publish/{platform}/validate')
    def validate(platform: str,draft: Draft) -> dict:
        if platform not in PUBLISHERS: raise HTTPException(404)
        return {'errors':PUBLISHERS[platform].validate(draft),'supported':False,'message':'资料校验不代表上架，真实发布暂不支持、需要官方授权'}
    @app.post('/api/publish/{platform}')
    def publish(platform: str) -> None: raise HTTPException(409,'暂不支持真实发布，需要官方授权及人工确认流程')
    @app.get('/api/settings')
    def settings() -> dict:
        return {'storage':'data/webapp（可通过 PRODUCT_TOOL_DATA 更改）','image_types':{'main':'支持','sku':'待支持：现有爬虫未提供','detail':'待支持：现有爬虫未提供'},'binding':'127.0.0.1','max_image_mb':15}
    return app
