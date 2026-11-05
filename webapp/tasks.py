"""Serial crawl/download queue and cancellable process trees."""
from __future__ import annotations
import http.client
import json
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from .store import Store, now
from . import images

ROOT = Path(__file__).resolve().parent.parent


def terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None: return
    if os.name == 'nt':
        subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    else:
        try: os.killpg(proc.pid,signal.SIGTERM)
        except ProcessLookupError: return
    try: proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name != 'nt': os.killpg(proc.pid,signal.SIGKILL)
        else: proc.kill()
        proc.wait()


def launch(args: list[str]) -> subprocess.Popen:
    child_env = os.environ.copy()
    child_env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    return subprocess.Popen(args,cwd=ROOT,env=child_env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                            start_new_session=os.name!='nt')


class TaskManager:
    def __init__(self, store: Store) -> None:
        self.store=store
        self.lock=threading.RLock()
        self.active: dict = {}
        self.cancel=threading.Event()
        self.proc: subprocess.Popen | None=None
        self.thread: threading.Thread | None=None
        self.logins: dict[str,subprocess.Popen]={}
        self.login_reports: dict[str,Path]={}
        for t in store.tasks():
            if t['status'] in ('running','stopping'):
                t['status']='interrupted'; t['message']='上次服务已退出，任务中断'; store.save_task(t)

    def start(self, kind: str, payload: dict) -> dict:
        with self.lock:
            if self.thread and self.thread.is_alive(): raise ValueError('已有任务执行中，请等待完成或停止')
            if any(p.poll() is None for p in self.logins.values()): raise ValueError('请先完成登录窗口操作')
            self.cancel.clear()
            self.active={'id':uuid.uuid4().hex,'kind':kind,'status':'running','created_at':now(),
                         'completed':0,'total':len(payload['ids']) if kind in ('images','details') else len(payload['keywords'])*len(payload['platforms']),
                         'counts':{},'failures':[],'message':'准备开始'}
            self.store.save_task(self.active)
            self.thread=threading.Thread(target=self.run,args=(kind,payload),daemon=True)
            self.thread.start()
            return dict(self.active)

    def save(self, **values: object) -> None:
        with self.lock:
            self.active.update(values); self.store.save_task(self.active)

    def run(self, kind: str, payload: dict) -> None:
        try:
            if kind in ('images','details'):
                for p in self.store.selected(payload['ids']):
                    if self.cancel.is_set(): break
                    if kind=='details':
                        self.save(message=f"正在补采商品详情和图集：{p['item_id']}")
                        if p['platform'] not in ('taobao','xianyu'):
                            p.update(detail_status='unsupported',detail_error='当前平台暂不支持详情图集采集')
                        elif not (ROOT/'state'/f"{p['platform']}_state.json").exists():
                            p.update(detail_status='failed',detail_error='请先登录对应平台再补采详情')
                        else:
                            out=self.store.root/f'{self.active["id"]}-detail.json'
                            with self.lock:
                                if self.cancel.is_set(): break
                                self.proc=launch([sys.executable,'-m','webapp.details',p['item_id'],str(out),p['platform']])
                            try: self.proc.wait(timeout=90)
                            except subprocess.TimeoutExpired: terminate(self.proc)
                            if self.cancel.is_set():
                                out.unlink(missing_ok=True); break
                            if out.exists(): p.update(json.loads(out.read_text(encoding='utf-8')))
                            else: p.update(detail_status='failed',detail_error='详情采集超时或进程未返回结果')
                            out.unlink(missing_ok=True)
                        self.store.upsert(p,p['keyword'])
                        if p.get('detail_error'):
                            self.active['failures'].append({'item_id':p['item_id'],'error':p['detail_error']})
                    if kind=='images': self.download_product(p,payload.get('image_ids'))
                    self.save(completed=self.active['completed']+1)
                    if kind=='details' and self.active['completed']<self.active['total']: self.cancel.wait(4.5)
            else:
                for platform in payload['platforms']:
                    for keyword in payload['keywords']:
                        if self.cancel.is_set(): break
                        self.save(message=f'正在采集 {platform} / {keyword}，请求 {payload["pages"]} 页（等待真实结果）')
                        state=ROOT/'state'/f'{platform}_state.json'
                        if not state.exists():
                            self.active['failures'].append({'platform':platform,'keyword':keyword,'error':'未保存登录状态，请先打开登录窗口'})
                            self.save(completed=self.active['completed']+1); continue
                        out=self.store.root/f'{self.active["id"]}-result.json'
                        with self.lock:
                            if self.cancel.is_set(): break
                            self.proc=launch([sys.executable,'-m','webapp.worker',platform,keyword,str(payload['pages']),str(out)])
                        deadline=time.monotonic()+1800
                        while self.proc.poll() is None:
                            if self.cancel.is_set() or time.monotonic()>deadline:
                                terminate(self.proc); break
                            if out.exists():
                                try:
                                    progress=json.loads(out.read_text(encoding='utf-8'))
                                    if progress.get('detail_total'):
                                        self.save(message=f"{platform} / {keyword}：详情图集已完成 {progress.get('detail_completed',0)}/{progress['detail_total']} 件")
                                except (OSError,ValueError):
                                    self.save(message='正在等待详情采集进度')
                            self.cancel.wait(.5)
                        if self.cancel.is_set():
                            if out.exists():
                                partial=json.loads(out.read_text(encoding='utf-8'))
                                for product in partial.get('products',[]): self.store.upsert(product,keyword)
                                self.active['counts'][platform]=self.active['counts'].get(platform,0)+len(partial.get('products',[]))
                            out.unlink(missing_ok=True); break
                        result=json.loads(out.read_text(encoding='utf-8')) if out.exists() else {'success':False,'error':'采集进程退出或超时，未产生报告'}
                        out.unlink(missing_ok=True)
                        if result['success']:
                            for product in result['products']:
                                if self.cancel.is_set(): break
                                self.store.upsert(product,keyword)
                                if product.get('detail_status') in ('failed','pending') or product.get('detail_error'):
                                    self.active['failures'].append({'item_id':product['item_id'],'error':product.get('detail_error') or '图集尚未采集完成，请补采详情'})
                            self.active['counts'][platform]=self.active['counts'].get(platform,0)+len(result['products'])
                            if not result['products']:
                                self.active['failures'].append({'platform':platform,'keyword':keyword,'error':'返回零条商品，可能没有匹配结果或平台限制访问'})
                        else:
                            self.active['failures'].append({'platform':platform,'keyword':keyword,'error':result['error']})
                        self.save(completed=self.active['completed']+1)
                        # Preserve conservative pacing between independent invocations.
                        if self.active['completed'] < self.active['total']:
                            self.save(message='采集间隔等待（保护账号），可随时停止')
                            self.cancel.wait(30)
            self.save(status='stopped' if self.cancel.is_set() else ('completed_with_errors' if self.active['failures'] else 'completed'),message='已停止' if self.cancel.is_set() else '任务已结束')
        except Exception:
            self.save(status='failed',message='任务异常结束，请检查本地文件权限、磁盘空间或输入数据')

    def download_product(self, product: dict, image_ids: list[int] | None = None) -> None:
        gallery=self.store.gallery(product['id'])
        if not gallery:
            self.store.image_result(product['id'],None,'搜索结果未提供主图')
            self.active['failures'].append({'item_id':product['item_id'],'error':'搜索结果未提供图片'})
        for image in gallery:
            if self.cancel.is_set(): break
            if image_ids is not None and image['id'] not in image_ids: continue
            if image['status']=='downloaded' and image['path'] and (self.store.root/image['path']).is_file(): continue
            self.save(message=f"正在下载商品 {product['item_id']} 图片 {image['position']+1}/{len(gallery)}")
            try:
                path=images.download(self.store.root,{**product,'image_url':image['url']},self.cancel)
                self.store.gallery_result(image['id'],path,None)
            except (ValueError,OSError,http.client.HTTPException) as exc:
                error=str(exc) if isinstance(exc,ValueError) else '网络、TLS 或文件读写失败，请重试'
                self.store.gallery_result(image['id'],None,error)
                self.active['failures'].append({'item_id':product['item_id'],'error':f"图片 {image['position']+1}：{error}"})

    def stop(self) -> None:
        with self.lock:
            self.cancel.set()
            if self.proc: terminate(self.proc)
            if self.thread and self.thread.is_alive(): self.save(status='stopping',message='正在停止，图片请求最多等待当前超时')

    def login(self, platform: str) -> None:
        with self.lock:
            if self.thread and self.thread.is_alive(): raise ValueError('采集或下载期间不能修改登录状态')
            if any(p.poll() is None for p in self.logins.values()): raise ValueError('已有登录窗口打开')
            report = self.store.root / f'login-{platform}-{uuid.uuid4().hex}.json'
            previous = self.login_reports.get(platform)
            if previous: previous.unlink(missing_ok=True)
            self.login_reports[platform] = report
            self.logins[platform]=launch([sys.executable,'-m','webapp.login_worker',platform,str(report)])

    def close(self) -> None:
        self.stop()
        for p in self.logins.values(): terminate(p)
        if self.thread: self.thread.join(timeout=25)
