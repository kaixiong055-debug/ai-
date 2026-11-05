from pathlib import Path
from webapp.store import Store

def test_gallery_storage(tmp_path: Path):
    store=Store(tmp_path)
    p={'platform':'xianyu','item_id':'42','title':'多图','image_url':'https://img.alicdn.com/cover.jpg',
       'gallery':['https://img.alicdn.com/a.jpg','https://img.alicdn.com/b.jpg','https://img.alicdn.com/a.jpg'],
       'description':'完整描述','detail_status':'collected','detail_error':None}
    pid=store.upsert(p,'词')
    assert len(store.gallery(pid))==3
    store.upsert(p,'词')
    assert len(store.gallery(pid))==3
    assert store.selected([pid])[0]['description']=='完整描述'

def test_detail_parser():
    from webapp.details import parse_detail
    data={'data':{'itemDO':{'itemId':42,'desc':'商品描述','imageInfos':[{'url':'http://img.alicdn.com/a.jpg'},{'url':'//img.alicdn.com/b.jpg'},{'url':'http://img.alicdn.com/a.jpg'}]}}}
    r=parse_detail(data,'42')
    assert len(r['gallery'])==2
    assert r['description']=='商品描述'
    assert parse_detail(data,'43') is None

def test_gallery_download_selection_and_export(tmp_path,monkeypatch):
    import io,zipfile
    from PIL import Image
    from fastapi.testclient import TestClient
    from webapp.app import create_app
    from webapp import images
    b=io.BytesIO();Image.new('RGB',(10,10),'blue').save(b,format='PNG')
    monkeypatch.setattr(images,'fetch_image',lambda url,**kwargs:b.getvalue())
    app=create_app(tmp_path)
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        c.headers['X-Local-Tool']='1'
        pid=app.state.store.upsert({'platform':'xianyu','item_id':'x','title':'test','image_url':'https://img.alicdn.com/a','gallery':['https://img.alicdn.com/b']},'k')
        gallery=c.get(f'/api/products/{pid}').json()['gallery']
        c.post('/api/gallery/download',json={'ids':[gallery[1]['id']]});app.state.tasks.thread.join(5)
        updated=c.get(f'/api/products/{pid}').json()['gallery']
        assert updated[0]['status']=='pending' and updated[1]['status']=='downloaded'
        assert c.get(f"/api/gallery/{gallery[1]['id']}").content==b.getvalue()
        z=zipfile.ZipFile(io.BytesIO(c.post('/api/export/zip',json={'ids':[pid]}).content))
        assert len([n for n in z.namelist() if n.endswith('.png')])==1
        assert any(n.endswith('/图片清单.csv') for n in z.namelist())
        c.post('/api/images/download',json={'ids':[pid]});app.state.tasks.thread.join(5)
        assert all(i['status']=='downloaded' for i in c.get(f'/api/products/{pid}').json()['gallery'])
        # Same bytes are stored once per product, even when URLs differ.
        assert len(list(tmp_path.glob('images/**/*.*')))==1


def test_existing_database_migration_preserves_main(tmp_path):
    import sqlite3
    db=tmp_path/'products.db'
    with sqlite3.connect(db) as c:
        c.execute('''CREATE TABLE products(id INTEGER PRIMARY KEY,platform TEXT,item_id TEXT,title TEXT,url TEXT,current_price REAL,image_url TEXT,keyword TEXT,crawled_at TEXT,image_path TEXT,image_status TEXT,image_error TEXT,UNIQUE(platform,item_id))''')
        c.execute("INSERT INTO products(id,platform,item_id,title,image_url,image_path,image_status) VALUES(1,'xianyu','x','old','https://img.alicdn.com/a','images/old.jpg','downloaded')")
    store=Store(tmp_path)
    assert store.gallery(1)[0]['path']=='images/old.jpg'
    assert store.gallery(1)[0]['status']=='downloaded'
    assert len(Store(tmp_path).gallery(1))==1

def test_detail_browser_collects_only_matching_item():
    from webapp.details import collect
    class Response:
        url='https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/'
        def json(self):
            return {'data':{'itemDO':{'itemId':'42','desc':'文字','imageInfos':[{'url':'https://img.alicdn.com/a'},{'url':'https://img.alicdn.com/b'}]}}}
    class Page:
        url='https://www.goofish.com/item?id=42'
        closed=False
        def on(self,event,handler): self.handler=handler
        def goto(self,url,**kwargs):
            assert url=='https://www.goofish.com/item?id=42'
            self.handler(Response())
        def is_closed(self): return self.closed
        def close(self): self.closed=True
    page=Page()
    class Context:
        def new_page(self): return page
    result=collect(Context(),'42')
    assert result['detail_status']=='collected' and len(result['gallery'])==2
    assert page.closed


def test_detail_browser_login_restriction():
    from webapp.details import collect
    class Page:
        url='https://login.taobao.com/'
        def on(self,*args): return None
        def goto(self,*args,**kwargs): return None
        def is_closed(self): return False
        def close(self): return None
    class Context:
        def new_page(self): return Page()
    result=collect(Context(),'42')
    assert result['detail_status']=='failed'
    assert '登录' in result['detail_error']
    assert 'gallery' not in result

def test_failed_extra_image_is_filterable(tmp_path):
    store=Store(tmp_path)
    pid=store.upsert({'platform':'xianyu','item_id':'x','title':'x','image_url':'https://img.alicdn.com/a','gallery':['https://img.alicdn.com/b']},'k')
    gallery=store.gallery(pid)
    store.gallery_result(gallery[0]['id'],'images/main.jpg',None)
    store.gallery_result(gallery[1]['id'],None,'失败')
    assert store.products(status='failed')['total']==1
    assert store.products(status='downloaded')['total']==0
    assert store.products(status='available')['total']==1


def test_old_cover_cannot_overwrite_current_cover(tmp_path):
    store=Store(tmp_path)
    p={'platform':'xianyu','item_id':'x','title':'x','image_url':'https://img.alicdn.com/a'}
    pid=store.upsert(p,'k'); old=store.gallery(pid)[0]
    p['image_url']='https://img.alicdn.com/b';store.upsert(p,'k')
    new=store.gallery(pid)[1]
    store.gallery_result(new['id'],'images/new.jpg',None)
    store.gallery_result(old['id'],'images/old.jpg',None)
    assert store.selected([pid])[0]['image_path']=='images/new.jpg'
    assert sum(i['kind']=='main' for i in store.gallery(pid))==1
