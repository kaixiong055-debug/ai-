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
    assert any(n.endswith('/商品介绍.txt') for n in zipfile.ZipFile(io.BytesIO(r.content)).namelist())
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
    assert len([n for n in archive.namelist() if n.endswith('.png')])==1
    assert any(n.endswith('/商品信息.json') for n in archive.namelist())
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

def test_crawl_import_does_not_download(client,monkeypatch,tmp_path):
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
    assert client.get('/api/products').json()['items'][0]['image_status']=='pending'
    assert not (client.app.state.store.root/'images').exists()
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

def test_product_details_and_safe_preview(client,monkeypatch):
    from PIL import Image
    from webapp import images
    b=io.BytesIO();Image.new('RGB',(30,20),'green').save(b,format='PNG')
    monkeypatch.setattr(images,'fetch_image',lambda url:b.getvalue())
    pid=client.app.state.store.upsert({'platform':'xianyu','item_id':'detail','title':'详情商品','image_url':'https://img.alicdn.com/a.png'},'关键词')
    assert client.get(f'/api/products/{pid}').json()['title']=='详情商品'
    assert client.get(f'/api/images/{pid}/preview').headers['content-type']=='image/jpeg'
    assert client.get(f'/api/products/{pid}').json()['image_status']=='pending'
    assert client.get('/api/products/999999').status_code==404

def test_available_and_no_image_filters(client):
    seed(client)
    client.app.state.store.upsert({'platform':'xianyu','item_id':'available','title':'可下载','image_url':'https://img.alicdn.com/a.png'},'k')
    assert client.get('/api/products?status=available').json()['total']==1
    assert client.get('/api/products?status=unavailable').json()['total']==1

def test_stop_preserves_collected_detail_results(client,monkeypatch,tmp_path):
    import sys,time,json
    import webapp.tasks as tasks
    (tmp_path/'state').mkdir();(tmp_path/'state'/'xianyu_state.json').write_text('{}',encoding='utf-8')
    monkeypatch.setattr(tasks,'ROOT',tmp_path)
    original=tasks.launch
    payload={'success':True,'products':[{'platform':'xianyu','item_id':'partial','title':'已采集','image_url':'https://img.alicdn.com/a','gallery':['https://img.alicdn.com/b'],'detail_status':'collected'}]}
    def worker(args):
        return original([sys.executable,'-c','import pathlib,sys,time;pathlib.Path(sys.argv[1]).write_text(sys.argv[2],encoding="utf-8");time.sleep(60)',args[-1],json.dumps(payload)])
    monkeypatch.setattr(tasks,'launch',worker)
    client.post('/api/tasks',json={'keywords':['k'],'platforms':['xianyu'],'pages':1})
    deadline=time.monotonic()+5
    while not list(client.app.state.store.root.glob('*-result.json')) and time.monotonic()<deadline:time.sleep(.02)
    client.post('/api/tasks/stop',json={});client.app.state.tasks.thread.join(5)
    assert client.get('/api/tasks').json()[0]['status']=='stopped'
    products=client.get('/api/products').json()['items']
    assert products[0]['item_id']=='partial'
    assert len(client.app.state.store.gallery(products[0]['id']))==2

def test_detail_collection_does_not_download(client,monkeypatch,tmp_path):
    import sys,json
    import webapp.tasks as tasks
    from webapp import images
    def unexpected(*args,**kwargs): raise AssertionError('采集不能下载')
    monkeypatch.setattr(images,'fetch_image',unexpected)
    (tmp_path/'state').mkdir();(tmp_path/'state'/'taobao_state.json').write_text('{}',encoding='utf-8')
    monkeypatch.setattr(tasks,'ROOT',tmp_path)
    pid=seed(client)
    from unittest.mock import Mock
    session=Mock()
    session.collect.return_value={'detail_status':'collected','description':'介绍','gallery':['https://img.alicdn.com/a','https://img.alicdn.com/b']}
    monkeypatch.setattr('webapp.detail_session.DetailSession',Mock(return_value=session))
    client.post('/api/details/collect',json={'ids':[pid]});client.app.state.tasks.thread.join(5)
    assert client.get('/api/tasks').json()[0]['status']=='completed'
    gallery=client.get(f'/api/products/{pid}').json()['gallery']
    assert len(gallery)==2 and all(i['status']=='pending' for i in gallery)
    assert not (client.app.state.store.root/'images').exists()

def test_export_product_folders_and_description(client,monkeypatch):
    from PIL import Image
    from webapp import images
    b=io.BytesIO();Image.new('RGB',(5,5),'blue').save(b,format='PNG')
    monkeypatch.setattr(images,'fetch_image',lambda *a,**k:b.getvalue())
    pid=client.app.state.store.upsert({'platform':'xianyu','item_id':'42','title':'机械键盘','description':'原始商品介绍\n支持热插拔','image_url':'https://img.alicdn.com/a','gallery':['https://img.alicdn.com/b']},'数码')
    gallery=client.app.state.store.gallery(pid)
    client.post('/api/gallery/download',json={'ids':[gallery[0]['id']]});client.app.state.tasks.thread.join(5)
    def no_network(*args,**kwargs): raise AssertionError('导出不能下载图片')
    monkeypatch.setattr(images,'fetch_image',no_network)
    r=client.post('/api/export/zip',json={'ids':[pid]})
    z=zipfile.ZipFile(io.BytesIO(r.content))
    names=z.namelist();prefix='闲鱼/数码/机械键盘/'
    assert all(n.startswith(prefix) for n in names)
    assert prefix+'001_封面.png' in names
    assert '支持热插拔' in z.read(prefix+'商品介绍.txt').decode('utf-8-sig')
    assert '未下载' in z.read(prefix+'图片清单.csv').decode('utf-8-sig')
    assert len([n for n in names if n.endswith('.png')])==1
    assert client.app.state.store.gallery(pid)[1]['status']=='pending'

def test_export_unsafe_and_duplicate_names(client):
    ids=[]
    for item_id in ['1','2']:
        ids.append(client.app.state.store.upsert({'platform':'taobao','item_id':item_id,'title':'../CON:商品?'},'../类别'))
    z=zipfile.ZipFile(io.BytesIO(client.post('/api/export/zip',json={'ids':ids}).content))
    paths=z.namelist()
    assert len(paths)==len(set(paths))
    assert len([p for p in paths if p.endswith('商品介绍.txt')])==2
    assert all(not p.startswith('/') and '..' not in p.split('/') and ':' not in p for p in paths)

def test_export_missing_local_file_is_honest(client):
    pid=client.app.state.store.upsert({'platform':'taobao','item_id':'missing','title':'缺图','image_url':'https://img.alicdn.com/a'},'关键词')
    with client.app.state.store.connect() as c:
        c.execute("UPDATE product_images SET status='downloaded',path=NULL WHERE product_id=?",(pid,))
    z=zipfile.ZipFile(io.BytesIO(client.post('/api/export/zip',json={'ids':[pid]}).content))
    manifest=next(p for p in z.namelist() if p.endswith('图片清单.csv'))
    assert '本地文件缺失' in z.read(manifest).decode('utf-8-sig')

def test_list_task_completes_without_details_and_preserves_previous_details(client,monkeypatch,tmp_path):
    import sys,json
    import webapp.tasks as tasks
    (tmp_path/'state').mkdir()
    (tmp_path/'state'/'xianyu_state.json').write_text('{}',encoding='utf-8')
    monkeypatch.setattr(tasks,'ROOT',tmp_path)
    store=client.app.state.store
    pid=store.upsert({'platform':'xianyu','item_id':'old','title':'旧商品','description':'保留描述',
                      'detail_status':'collected','gallery':['https://img.alicdn.com/a']},'k')
    original=tasks.launch
    payload={'success':True,'products':[{'platform':'xianyu','item_id':i,'title':'列表商品'} for i in ('old','new')]}
    def worker(args):
        return original([sys.executable,'-c','import pathlib,sys;pathlib.Path(sys.argv[1]).write_text(sys.argv[2],encoding="utf-8")',args[-1],json.dumps(payload)])
    monkeypatch.setattr(tasks,'launch',worker)
    client.post('/api/tasks',json={'keywords':['k'],'platforms':['xianyu'],'pages':1})
    client.app.state.tasks.thread.join(5)
    task=client.get('/api/tasks').json()[0]
    assert task['status']=='completed' and task['failures']==[]
    assert task['counts']=={'xianyu':2}
    old=client.get(f'/api/products/{pid}').json()
    assert old['detail_status']=='collected' and old['description']=='保留描述'
    assert len(old['gallery'])==1
    assert not (store.root/'images').exists()

def test_picker_exposes_finished_details_while_batch_still_running(client,monkeypatch):
    store=client.app.state.store
    first=store.upsert({'platform':'taobao','item_id':'101','title':'完成商品','detail_status':'collected','description':'立即可读'},'k')
    second=store.upsert({'platform':'taobao','item_id':'102','title':'处理中'},'k')
    monkeypatch.setattr(client.app.state.picker,'status',lambda:{'status':'ready','candidates':[
        {'platform':'taobao','item_id':'101'}, {'platform':'taobao','item_id':'102'}]})
    client.app.state.tasks.active={'kind':'details','status':'running','item_states':{str(first):'collected',str(second):'running'}}
    cards=client.get('/api/selection/browser').json()['candidates']
    assert cards[0]['collection_status']=='collected'
    assert cards[0]['product_id']==first
    assert cards[1]['collection_status']=='running'
    assert client.get(f'/api/products/{first}').json()['description']=='立即可读'
    client.app.state.tasks.active['status']='stopped'
    assert client.get('/api/selection/browser').json()['candidates'][1]['collection_status']=='pending'
    client.app.state.tasks.active={}

def test_original_endpoint_reuses_tool_and_rejects_external_links(client,monkeypatch):
    from unittest.mock import Mock
    picker=client.app.state.picker
    picker.proc=Mock();picker.proc.poll.return_value=None;picker.platform='taobao'
    monkeypatch.setattr(picker,'send',Mock(return_value={'status':'busy'}))
    assert client.post('/api/selection/browser/product',json={'url':'https://item.taobao.com/item.htm?id=123'}).status_code==200
    assert picker.send.call_args.args[0]['action']=='open_product'
    assert client.post('/api/selection/browser/product',json={'url':'https://evil.com'}).status_code==409
    picker.proc=None


def test_detail_auth_failure_stops_batch_before_next_item(client,monkeypatch,tmp_path):
    from unittest.mock import Mock
    import webapp.tasks as tasks
    (tmp_path/'state').mkdir();(tmp_path/'state'/'taobao_state.json').write_text('{}')
    monkeypatch.setattr(tasks,'ROOT',tmp_path)
    ids=[client.app.state.store.upsert({'platform':'taobao','item_id':str(i),'title':'商品'},'k') for i in (1,2)]
    session=Mock();session.collect.return_value={'detail_status':'failed','detail_error':'需要验证','auth_required':True}
    factory=Mock(return_value=session)
    monkeypatch.setattr('webapp.detail_session.DetailSession',factory)
    client.post('/api/details/collect',json={'ids':ids});client.app.state.tasks.thread.join(5)
    assert session.collect.call_count==1
    session.close.assert_called_once()
    task=client.get('/api/tasks').json()[0]
    assert task['status']=='completed_with_errors' and task['completed']==1
    assert client.get(f'/api/products/{ids[1]}').json()['detail_status']=='pending'

def test_detail_batch_reuses_session_and_saves_each_product(client,monkeypatch,tmp_path):
    from unittest.mock import Mock
    import webapp.tasks as tasks
    (tmp_path/'state').mkdir();(tmp_path/'state'/'taobao_state.json').write_text('{}')
    monkeypatch.setattr(tasks,'ROOT',tmp_path)
    monkeypatch.setattr(tasks,'DETAIL_MIN_INTERVAL_SECONDS',0)
    store=client.app.state.store
    ids=[store.upsert({'platform':'taobao','item_id':str(i),'title':'商品'},'k') for i in (1,2)]
    def collect(item_id,cancel):
        if item_id=='2':assert store.selected([ids[0]])[0]['description']=='详情1'
        return {'detail_status':'collected','description':'详情'+item_id}
    session=Mock();session.collect.side_effect=collect
    factory=Mock(return_value=session)
    monkeypatch.setattr('webapp.detail_session.DetailSession',factory)
    client.post('/api/details/collect',json={'ids':ids});client.app.state.tasks.thread.join(5)
    assert factory.call_count==1 and session.collect.call_count==2
    assert client.get('/api/tasks').json()[0]['status']=='completed'
    assert store.selected([ids[1]])[0]['description']=='详情2'

def test_detail_mode_defaults_background_and_validates_opt_in(client,monkeypatch):
    from unittest.mock import Mock
    start=Mock(return_value={'status':'running'})
    monkeypatch.setattr(client.app.state.tasks,'start',start)
    assert client.post('/api/details/collect',json={'ids':[1]}).status_code==200
    assert start.call_args.args[1]['mode']=='background'
    assert client.post('/api/details/collect',json={'ids':[1],'mode':'compatible'}).status_code==200
    assert start.call_args.args[1]['mode']=='compatible'
    assert client.post('/api/details/collect',json={'ids':[1],'mode':'automatic'}).status_code==422

def test_tmall_original_url_reaches_detail_session(client,monkeypatch,tmp_path):
    from unittest.mock import Mock
    import webapp.tasks as tasks
    (tmp_path/'state').mkdir();(tmp_path/'state'/'taobao_state.json').write_text('{}')
    monkeypatch.setattr(tasks,'ROOT',tmp_path)
    url='https://detail.tmall.com/item.htm?id=926199962521'
    pid=client.app.state.store.upsert({'platform':'taobao','item_id':'926199962521','title':'商品','url':url},'k')
    session=Mock();session.collect.return_value={'detail_status':'collected','description':'详情'}
    monkeypatch.setattr('webapp.detail_session.DetailSession',Mock(return_value=session))
    client.post('/api/details/collect',json={'ids':[pid]});client.app.state.tasks.thread.join(5)
    assert session.collect.call_args.kwargs['url']==url
    assert client.get('/api/tasks').json()[0]['status']=='completed'
