from pathlib import Path
import io
import zipfile
import pytest
from fastapi.testclient import TestClient
from webapp.app import create_app
from webapp.images import validate_url, verify_image

@pytest.fixture
def client(tmp_path: Path):
    app = create_app(tmp_path)
    with TestClient(app, base_url='http://127.0.0.1:8765') as c:
        c.headers['X-Local-Tool'] = '1'
        yield c

def seed(client):
    return client.app.state.store.upsert({'platform':'taobao','item_id':'123','title':'测试商品','url':'https://item.taobao.com/item.htm?id=123','current_price':12.5,'image_url':None}, '测试')

def test_persistence_dedup_filters(client):
    seed(client); seed(client)
    result = client.get('/api/products').json()
    assert result['total'] == 1
    assert client.get('/api/products?q=不存在').json()['total'] == 0
    assert client.get('/api/products?platform=xianyu').json()['total'] == 0

def test_export_draft_delete(client):
    pid = seed(client)
    assert '测试商品' in client.post('/api/export/csv',json={'ids':[pid]}).content.decode('utf-8-sig')
    r=client.post('/api/export/zip',json={'ids':[pid]})
    assert 'products.csv' in zipfile.ZipFile(io.BytesIO(r.content)).namelist()
    assert client.post('/api/drafts',json={'ids':[pid]}).status_code == 200
    assert len(client.get('/api/drafts').json()) == 1
    assert client.post('/api/publish/taobao',json={}).status_code == 409
    assert client.post('/api/products/delete',json={'ids':[pid]}).status_code == 200
    assert client.get('/api/products').json()['total']==0

@pytest.mark.parametrize('url',['file:///etc/passwd','http://127.0.0.1/a','https://localhost/a','https://evil.com/a','https://img.alicdn.com@evil.com/a'])
def test_url_rejection(url):
    with pytest.raises(ValueError): validate_url(url)

def test_invalid_image():
    with pytest.raises(ValueError): verify_image(b'<html>login</html>')

def test_local_security(client):
    assert client.get('/state/taobao_state.json').status_code == 404
    assert client.post('/api/tasks',json={},headers={'Origin':'https://evil.com'}).status_code == 403
    assert client.get('/api/health',headers={'Host':'evil.com'}).status_code == 400

def test_page_and_accounts(client):
    assert client.get('/').status_code == 200
    assert 'cookie' not in client.get('/api/accounts').text.lower()

def test_image_download_and_zip(client, monkeypatch):
    from PIL import Image
    from webapp import images
    b=io.BytesIO(); Image.new('RGB',(20,20),'blue').save(b,format='PNG')
    monkeypatch.setattr(images,'fetch_image',lambda url, **kwargs:b.getvalue())
    pid=client.app.state.store.upsert({'platform':'taobao','item_id':'img','title':'图片测试','image_url':'https://img.alicdn.com/test.png'},'../关键字')
    assert client.post('/api/images/download',json={'ids':[pid]}).status_code==200
    client.app.state.tasks.thread.join(5)
    p=client.get('/api/products').json()['items'][0]
    assert p['image_status']=='downloaded'
    assert client.get(f'/api/images/{pid}').content==b.getvalue()
    archive=zipfile.ZipFile(io.BytesIO(client.post('/api/export/zip',json={'ids':[pid]}).content))
    assert len(archive.namelist())==2
    first=p['image_path']
    client.post('/api/images/download',json={'ids':[pid]}); client.app.state.tasks.thread.join(5)
    assert client.get('/api/products').json()['items'][0]['image_path']==first

def test_failure_record_and_restart(client):
    pid=seed(client)
    client.post('/api/images/download',json={'ids':[pid]}); client.app.state.tasks.thread.join(5)
    assert client.get('/api/products').json()['items'][0]['image_status']=='failed'
    from webapp.store import Store
    assert Store(client.app.state.store.root).products()['total']==1

def test_crawl_no_login_honest_failure(client,monkeypatch,tmp_path):
    import webapp.tasks as tasks
    monkeypatch.setattr(tasks,'ROOT',tmp_path)
    r=client.post('/api/tasks',json={'keywords':['测试'],'platforms':['taobao'],'pages':1})
    assert r.status_code==200
    client.app.state.tasks.thread.join(5)
    t=client.get('/api/tasks').json()[0]
    assert t['status']=='completed_with_errors'
    assert '登录' in t['failures'][0]['error']
    assert client.get('/api/products').json()['total']==0

def test_draft_edit_and_validation(client):
    pid=seed(client);client.post('/api/drafts',json={'ids':[pid]})
    d=client.get('/api/drafts').json()[0];d.update(title='修改标题',platforms=['taobao'])
    assert client.put('/api/drafts/'+str(d['id']),json=d).status_code==200
    assert client.get('/api/drafts').json()[0]['title']=='修改标题'
    r=client.post('/api/publish/taobao/validate',json=d).json()
    assert r['supported'] is False and r['errors']

def test_csv_formula_escape(client):
    pid=client.app.state.store.upsert({'platform':'taobao','item_id':'formula','title':'=HYPERLINK("evil")'},'k')
    assert "'=HYPERLINK" in client.post('/api/export/csv',json={'ids':[pid]}).content.decode('utf-8-sig')

def test_unknown_draft_platform_rejected(client):
    pid=seed(client);client.post('/api/drafts',json={'ids':[pid]})
    d=client.get('/api/drafts').json()[0];d['platforms']=['unknown']
    assert client.put('/api/drafts/'+str(d['id']),json=d).status_code==422

def test_http_failure_recorded_per_image(client,monkeypatch):
    import http.client
    from webapp import images
    def broken(url, **kwargs): raise http.client.IncompleteRead(b'')
    monkeypatch.setattr(images,'fetch_image',broken)
    pid=client.app.state.store.upsert({'platform':'taobao','item_id':'broken','title':'bad','image_url':'https://img.alicdn.com/a'},'k')
    client.post('/api/images/download',json={'ids':[pid]});client.app.state.tasks.thread.join(5)
    assert client.get('/api/products').json()['items'][0]['image_status']=='failed'

def test_task_stop_terminates_process(client,monkeypatch,tmp_path):
    import time,sys
    import webapp.tasks as tasks
    (tmp_path/'state').mkdir();(tmp_path/'state'/'taobao_state.json').write_text('{}',encoding='utf-8')
    monkeypatch.setattr(tasks,'ROOT',tmp_path)
    original=tasks.launch
    monkeypatch.setattr(tasks,'launch',lambda args:original([sys.executable,'-c','import time; time.sleep(60)']))
    client.post('/api/tasks',json={'keywords':['a'],'platforms':['taobao'],'pages':1})
    deadline=time.monotonic()+3
    while client.app.state.tasks.proc is None and time.monotonic()<deadline: time.sleep(.01)
    client.post('/api/tasks/stop',json={})
    client.app.state.tasks.thread.join(5)
    assert client.app.state.tasks.proc.poll() is not None
    assert client.get('/api/tasks').json()[0]['status']=='stopped'

def test_crawl_import_auto_download(client,monkeypatch,tmp_path):
    import sys,json
    import webapp.tasks as tasks
    from webapp import images
    from PIL import Image
    b=io.BytesIO();Image.new('RGB',(10,10),'red').save(b,format='PNG')
    monkeypatch.setattr(images,'fetch_image',lambda url,**kwargs:b.getvalue())
    (tmp_path/'state').mkdir();(tmp_path/'state'/'taobao_state.json').write_text('{}',encoding='utf-8')
    monkeypatch.setattr(tasks,'ROOT',tmp_path)
    original=tasks.launch
    payload={'success':True,'products':[{'platform':'taobao','item_id':'auto','title':'自动主图','image_url':'https://img.alicdn.com/test.png'}]}
    def fake_worker(args):
        return original([sys.executable,'-c','import pathlib,sys;pathlib.Path(sys.argv[1]).write_text(sys.argv[2],encoding="utf-8")',args[-1],json.dumps(payload)])
    monkeypatch.setattr(tasks,'launch',fake_worker)
    client.post('/api/tasks',json={'keywords':['关键词'],'platforms':['taobao'],'pages':1})
    client.app.state.tasks.thread.join(5)
    assert client.get('/api/products').json()['items'][0]['image_status']=='downloaded'
    assert client.get('/api/tasks').json()[0]['counts']['taobao']==1

def test_child_process_forces_utf8(monkeypatch):
    import webapp.tasks as tasks
    captured={}
    def spawn(args,**kwargs):
        captured.update(kwargs)
        return object()
    monkeypatch.setattr(tasks.subprocess,'Popen',spawn)
    tasks.launch(['python','helper.py'])
    assert captured['env']['PYTHONIOENCODING']=='utf-8'
    assert captured['env']['PYTHONUTF8']=='1'

def test_login_diagnostics_do_not_expose_exception(tmp_path):
    from webapp.login_worker import run_login
    def fail(): raise RuntimeError('secret credential must not escape')
    assert run_login(fail,tmp_path/'state.json')=='unexpected_error'

def test_saved_state_survives_cleanup_failure(tmp_path):
    from webapp.login_worker import run_login
    state=tmp_path/'state.json'
    def login():
        state.write_text('{}',encoding='utf-8')
        raise RuntimeError('close failed')
    assert run_login(login,state)=='saved_with_warning'

def test_old_state_not_reported_as_new_success(tmp_path):
    from webapp.login_worker import run_login
    state=tmp_path/'state.json';state.write_text('{}',encoding='utf-8')
    assert run_login(lambda:False,state)=='not_completed'

def test_account_uses_safe_login_result(client):
    import json
    from types import SimpleNamespace
    manager=client.app.state.tasks
    report=manager.store.root/'login-test.json'
    report.write_text(json.dumps({'code':'encoding_error','secret':'DO_NOT_EXPOSE'}),encoding='utf-8')
    manager.logins['taobao']=SimpleNamespace(poll=lambda:1)
    manager.login_reports['taobao']=report
    response=client.get('/api/accounts')
    assert '字符编码错误' in response.text
    assert 'DO_NOT_EXPOSE' not in response.text

@pytest.mark.parametrize('url',[
    'http://img.alicdn.com/item.jpg?size=200',
    'http://img.alicdn.com:80/item.jpg?size=200',
    '//img.alicdn.com/item.jpg?size=200',
    'https://img.alicdn.com/item.jpg?size=200',
])
def test_cdn_legacy_urls_use_https_transport(url,monkeypatch):
    import socket
    from webapp import images
    # Use a globally routable fixture address for public-IP validation.
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('8.8.8.8',443))])
    calls=[]
    class Response:
        status=200
        def getheader(self,key): return 'image/png'
        def read1(self,n): return b''
    class Connection:
        def __init__(self,host,address): calls.append((host,address))
        def request(self,method,path,headers): calls.append((method,path))
        def getresponse(self): return Response()
        def close(self): return None
    monkeypatch.setattr(images,'PinnedHTTPS',Connection)
    images.fetch_image(url)
    assert calls==[('img.alicdn.com','8.8.8.8'),('GET','/item.jpg?size=200')]

@pytest.mark.parametrize('url',[
    'http://evil.com/a','http://img.alicdn.com.evil.com/a',
    'http://img.alicdn.com:8080/a','http://user:pass@img.alicdn.com/a',
    'https://img.alicdn.com:80/a','ftp://img.alicdn.com/a',
])
def test_http_upgrade_does_not_relax_url_security(url):
    with pytest.raises(ValueError): validate_url(url)

def test_http_cdn_private_dns_still_rejected(monkeypatch):
    import socket
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))])
    with pytest.raises(ValueError,match='本地或保留'): validate_url('http://img.alicdn.com/a')
