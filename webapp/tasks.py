"""Serial crawl/download queue and cancellable process trees."""
from __future__ import annotations
import http.client
import json
import os
import signal
import subprocess
import sys
import threading
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
                         'completed':0,'total':len(payload['ids']) if kind=='images' else len(payload['keywords'])*len(payload['platforms']),
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
            if kind=='images':
                for p in self.store.selected(payload['ids']):
                    if self.cancel.is_set(): break
                    self.save(message=f"正在下载主图：{p['item_id']}")
                    try:
                        path=images.download(self.store.root,p,self.cancel)
                        self.store.image_result(p['id'],path,None)
                    except (ValueError,OSError,http.client.HTTPException) as e:
                        error=str(e) if isinstance(e,ValueError) else '网络、TLS 或文件读写失败，请重试'
                        self.store.image_result(p['id'],None,error)
                        self.active['failures'].append({'item_id':p['item_id'],'error':error})
                    self.save(completed=self.active['completed']+1)
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
                        try:
                            self.proc.wait(timeout=1800)
                        except subprocess.TimeoutExpired:
                            terminate(self.proc)
                        if self.cancel.is_set():
                            out.unlink(missing_ok=True); break
                        result=json.loads(out.read_text(encoding='utf-8')) if out.exists() else {'success':False,'error':'采集进程退出或超时，未产生报告'}
                        out.unlink(missing_ok=True)
                        if result['success']:
                            for product in result['products']:
                                if self.cancel.is_set(): break
                                pid = self.store.upsert(product,keyword)
                                saved = self.store.selected([pid])[0]
                                if saved['image_status'] != 'downloaded':
                                    self.save(message=f'正在保存 {platform} / {keyword} 主图：{product["item_id"]}')
                                    try:
                                        path = images.download(self.store.root,saved,self.cancel)
                                        self.store.image_result(pid,path,None)
                                    except (ValueError,OSError,http.client.HTTPException) as e:
                                        error = str(e) if isinstance(e,ValueError) else '网络、TLS 或文件读写失败，请重试'
                                        self.store.image_result(pid,None,error)
                                        self.active['failures'].append({'platform':platform,'item_id':str(product['item_id']),'error':error})
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
