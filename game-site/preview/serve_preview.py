"""Local preview only; production output is a static website."""
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import threading
import webbrowser

if __name__=='__main__':
    root=Path(__file__).resolve().parent
    with ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(root))) as server:
        url=f'http://127.0.0.1:{server.server_port}/games/14545/'
        print('网页预览：'+url+'\n关闭本窗口或按 Ctrl+C 结束本地预览。',flush=True)
        threading.Timer(.6,lambda:webbrowser.open(url)).start()
        try:server.serve_forever()
        except KeyboardInterrupt:pass
