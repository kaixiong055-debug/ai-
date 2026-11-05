"""Strict public CDN download with TLS, bounded size and actual image decoding."""
from __future__ import annotations
import hashlib
import http.client
import io
import ipaddress
import re
import socket
import ssl
import time
from threading import Event
from pathlib import Path
from urllib.parse import urlsplit
from PIL import Image, UnidentifiedImageError

MAX_BYTES = 15 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 25_000_000


def validate_url(url: str) -> tuple[str, str, str]:
    if url.startswith('//'): url = 'https:' + url
    p = urlsplit(url)
    host = p.hostname or ''
    if p.scheme != 'https' or p.username or p.password or p.port not in (None,443):
        raise ValueError('仅允许 HTTPS 图片地址')
    if not any(host == d or host.endswith('.'+d) for d in ('alicdn.com','tbcdn.cn','taobaocdn.com')):
        raise ValueError('图片域名不在阿里图片 CDN 白名单')
    addresses = {r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(a).is_global for a in addresses):
        raise ValueError('禁止访问本地或保留网络地址')
    return host, next(iter(addresses)), (p.path or '/') + ('?'+p.query if p.query else '')


def verify_image(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format
            if fmt not in ('JPEG','PNG','WEBP','GIF'): raise ValueError('不支持的图片格式')
            img.verify()
        with Image.open(io.BytesIO(data)) as img:
            img.load()
        return {'JPEG':'jpg','PNG':'png','WEBP':'webp','GIF':'gif'}[fmt]
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
        raise ValueError('图片损坏或尺寸超限') from e


class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str) -> None:
        super().__init__(host, timeout=20, context=ssl.create_default_context())
        self.address = address

    def connect(self) -> None:
        raw = socket.create_connection((self.address,443),self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw,server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def fetch_image(url: str, cancel: Event | None = None) -> bytes:
    host,address,path = validate_url(url)
    conn = PinnedHTTPS(host,address)
    try:
        conn.request('GET',path,headers={'User-Agent':'LocalProductManager/1.0','Accept':'image/*'})
        response = conn.getresponse()
        if response.status != 200: raise ValueError(f'图片服务器返回 HTTP {response.status}（不跟随重定向）')
        if not (response.getheader('Content-Type') or '').lower().startswith('image/'):
            raise ValueError('响应不是图片')
        chunks = []
        size = 0
        deadline = time.monotonic() + 45
        while True:
            if cancel and cancel.is_set(): raise ValueError('下载已取消')
            if time.monotonic() >= deadline: raise ValueError('图片下载超过总时限')
            chunk = response.read1(min(65536, MAX_BYTES + 1 - size))
            if not chunk: break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_BYTES: raise ValueError('图片超过 15MB 限制')
        return b''.join(chunks)
    finally:
        conn.close()


def segment(value: str) -> str:
    clean = re.sub(r'[^\w\-\u4e00-\u9fff]', '_', value)[:48].strip(' .') or 'item'
    return clean + '-' + hashlib.sha256(value.encode()).hexdigest()[:8]


def download(root: Path, product: dict, cancel: Event | None = None) -> str:
    if not product.get('image_url'): raise ValueError('搜索结果未提供主图')
    data = fetch_image(product['image_url'], cancel=cancel)
    ext = verify_image(data)
    digest = hashlib.sha256(data).hexdigest()
    folder = root / 'images' / product['platform'] / segment(product['keyword']) / segment(product['item_id'])
    folder.mkdir(parents=True,exist_ok=True)
    path = folder / f'main-{digest[:20]}.{ext}'
    if not path.exists(): path.write_bytes(data)
    return path.relative_to(root).as_posix()
