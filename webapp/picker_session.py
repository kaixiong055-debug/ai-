"""Serialized control for the local selection browser; no raw browser logs are exposed."""
from __future__ import annotations
import json
import sys
import threading
import uuid
from pathlib import Path
from .tasks import launch, terminate
from .picker import write_json


class PickerSession:
    def __init__(self, root: Path) -> None:
        self.root=root
        self.lock=threading.RLock()
        self.proc=None
        self.folder: Path | None=None
        self.platform=''
        self.pending=''

    def status(self) -> dict:
        with self.lock:
            result={'status':'closed','message':'尚未打开选品浏览器','candidates':[],'pages':[]}
            if self.folder:
                try: result=json.loads((self.folder/'status.json').read_text(encoding='utf-8'))
                except (OSError,ValueError): result.update(status='starting',message='正在启动选品浏览器')
            if self.proc and self.proc.poll() is not None and result['status'] not in ('failed','closed'):
                result.update(status='closed',message='选品浏览器已关闭；已读取候选保留')
            elif self.pending and result.get('command_id')!=self.pending:
                result.update(status='busy',message='正在等待浏览器执行操作')
            return {**result,'platform':self.platform}

    def start(self, platform: str) -> dict:
        with self.lock:
            if platform not in ('taobao','xianyu'): raise ValueError('平台无效')
            if self.proc and self.proc.poll() is None: raise ValueError('请先关闭现有选品浏览器')
            self.folder=self.root/'picker'/uuid.uuid4().hex
            self.folder.mkdir(parents=True)
            self.platform=platform;self.pending=''
            self.proc=launch([sys.executable,'-m','webapp.picker',str(self.folder),platform])
            return self.status()

    def send(self, command: dict) -> dict:
        with self.lock:
            if not self.proc or self.proc.poll() is not None: raise ValueError('请先打开选品浏览器')
            if self.status()['status']!='ready': raise ValueError('浏览器正在执行操作，请等待完成或关闭浏览器停止')
            self.pending=uuid.uuid4().hex
            write_json(self.folder/'command.json',{**command,'id':self.pending})
            return self.status()

    def close(self) -> None:
        with self.lock:
            if self.proc: terminate(self.proc)
            self.pending=''
