"""One browser context per platform batch, or lease the live selection context."""
from __future__ import annotations
import json
import sys
import time
import uuid
from pathlib import Path
from .picker import write_json
from .tasks import terminate


class DetailSession:
    def __init__(self, root: Path, platform: str, launch: object, picker: object = None) -> None:
        self.platform=platform
        self.picker=picker
        self.closed=False
        self.borrowed=False
        self.proc=None
        if picker:
            with picker.lock:
                if picker.proc and picker.proc.poll() is None and picker.platform==platform:
                    if picker.status()['status']!='ready' or picker.leased:
                        raise ValueError('选品浏览器正在操作，请等待完成后再采集详情')
                    picker.leased=True
                    self.borrowed=True
                    self.folder=picker.folder
                    self.proc=picker.proc
        if not self.borrowed:
            self.folder=root/'detail-sessions'/uuid.uuid4().hex
            self.folder.mkdir(parents=True)
            self.proc=launch([sys.executable,'-m','webapp.detail_worker',str(self.folder),platform])

    def collect(self, item_id: str, cancel: object) -> dict:
        request_id=uuid.uuid4().hex
        command={'id':request_id,'action':'detail','item_id':item_id}
        if self.borrowed:
            self.picker.send(command,internal=True)
            request_id=self.picker.pending
        else: write_json(self.folder/'command.json',command)
        return self.wait_result(request_id,cancel)

    def wait_result(self, request_id: str, cancel: object) -> dict:
        deadline=time.monotonic()+90
        while not cancel.is_set() and time.monotonic()<deadline:
            try:
                report=json.loads((self.folder/'result.json').read_text(encoding='utf-8'))
                if report.get('request_id')==request_id: return report['result']
            except (OSError,ValueError): pass
            if self.proc.poll() is not None: break
            cancel.wait(.1)
        # A stuck page cannot consume later commands or keep an expired session alive.
        terminate(self.proc)
        return {'detail_status':'failed','detail_error':'详情任务已停止、超时或浏览器退出；已完成商品保留','session_failed':True}

    def close(self) -> None:
        if self.closed:return
        self.closed=True
        if self.borrowed:
            with self.picker.lock:self.picker.leased=False
        elif self.proc:
            # Graceful shutdown flushes refreshed cookies before terminating a stuck worker.
            write_json(self.folder/'command.json',{'id':uuid.uuid4().hex,'action':'close'})
            try:self.proc.wait(timeout=3)
            except Exception:terminate(self.proc)
