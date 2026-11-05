"""Start only on loopback; open browser after verified readiness."""
from __future__ import annotations
import json
import logging
import threading
import time
import urllib.request
import webbrowser
import uvicorn
from .app import create_app


def ready() -> bool:
    try:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8765/api/health',timeout=1) as r:
            return json.load(r).get('app')=='product-crawling-local'
    except (OSError,ValueError): return False


def open_when_ready() -> None:
    for _ in range(60):
        if ready():
            webbrowser.open('http://127.0.0.1:8765'); return
        time.sleep(.5)
    logging.error('服务未就绪，请查看终端错误，检查 8765 端口及数据目录权限。')


def main() -> None:
    if ready():
        webbrowser.open('http://127.0.0.1:8765'); return
    threading.Thread(target=open_when_ready,daemon=True).start()
    uvicorn.run(create_app(),host='127.0.0.1',port=8765,access_log=False)

if __name__=='__main__': main()
