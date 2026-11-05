"""Loopback-only management API; private files are never mounted."""
from __future__ import annotations
import http.client
import csv
import json
import io
import os
import zipfile
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware
from PIL import Image
from . import images
from .store import Store
from .tasks import TaskManager, ROOT
from .publishers import Draft, PUBLISHERS
from .login_worker import MESSAGES

class Selection(BaseModel):
    ids: list[int] = Field(min_length=1,max_length=1000)

class Search(BaseModel):
    keywords: list[str] = Field(min_length=1,max_length=20)
    platforms: list[str] = Field(min_length=1,max_length=2)
    pages: int = Field(1,ge=1,le=20)


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
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        tasks.close()
    app=FastAPI(title='商品采集管理',docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.store=store; app.state.tasks=tasks
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
    @app.get('/api/products')
    def products(q: str='',platform: str='',status: str='',page: int=Query(1,ge=1),size: int=Query(24,ge=1,le=100)) -> dict:
        return store.products(q,platform,status,page,size)
    @app.get('/api/products/{pid}')
    def detail(pid: int) -> dict:
        rows=store.selected([pid])
        if not rows: raise HTTPException(404,'商品不存在')
        return rows[0]
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
        try: tasks.login(platform)
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
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('products.csv',csv_data(rows))
            for p in rows:
                if p.get('image_path'):
                    path=(store.root/p['image_path']).resolve()
                    if path.is_relative_to(store.root/'images') and path.is_file(): z.write(path,p['image_path'])
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
