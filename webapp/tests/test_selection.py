import pytest

@pytest.mark.parametrize('url,platform,item_id',[
 ('https://www.goofish.com/item?id=123&spm=tracking','xianyu','123'),
 ('https://item.taobao.com/item.htm?id=456','taobao','456'),
 ('https://detail.tmall.com/item.htm?id=789','taobao','789'),
])
def test_product_link_canonical(url,platform,item_id):
    from webapp.selection import product_link
    p=product_link(url)
    assert p['platform']==platform and p['item_id']==item_id
    assert 'spm' not in p['url']

@pytest.mark.parametrize('url',['file:///tmp/x','http://127.0.0.1','https://evil.com/item?id=1','https://item.taobao.com.evil.com/item.htm?id=1','https://user:pw@item.taobao.com/item.htm?id=1'])
def test_reject_untrusted_links(url):
    from webapp.selection import product_link
    with pytest.raises(ValueError): product_link(url)


def test_link_import_does_not_destroy_existing_images(tmp_path):
    from webapp.store import Store
    from webapp.selection import import_links
    store=Store(tmp_path)
    pid=store.upsert({'platform':'taobao','item_id':'42','title':'原商品','image_url':'https://img.alicdn.com/a'},'原分类')
    ids=import_links(store,['https://item.taobao.com/item.htm?id=42','https://item.taobao.com/item.htm?id=42'],'新分类')
    assert ids==[pid]
    assert store.selected(ids)[0]['title']=='原商品'
    assert store.selected(ids)[0]['image_url']

def test_source_url_strips_secrets():
    from webapp.selection import source_link
    assert source_link('https://www.goofish.com/personal?userId=123&token=secret')=='https://www.goofish.com/personal?userId=123'

@pytest.mark.parametrize('url',['https://www.goofish.com/item?id=42','https://item.taobao.com/item.htm?id=42','https://www.taobao.com/'])
def test_shop_rejects_non_shop_page(url):
    from webapp.selection import store_page
    with pytest.raises(ValueError): store_page(url)

def test_extract_candidates_deduplicates_and_filters():
    from webapp.picker import extract_candidates
    class Links:
        def evaluate_all(self,script):
            return [{'url':'https://www.goofish.com/item?id=42&spm=x','title':'商品','image_url':None},
                    {'url':'https://www.goofish.com/item?id=42','title':'重复','image_url':None},
                    {'url':'https://evil.com/item?id=43','title':'恶意','image_url':None},
                    {'url':'https://item.taobao.com/item.htm?id=44','title':'其他平台','image_url':None}]
    class Page:
        def locator(self,selector): return Links()
    result=extract_candidates(Page(),'xianyu','https://www.goofish.com/personal?userId=1','卖家',100)
    assert len(result)==1 and result[0]['item_id']=='42'
    assert '归属未验证' in result[0]['ownership']


def test_link_import_api_and_candidates(tmp_path):
    from fastapi.testclient import TestClient
    from webapp.app import create_app
    app=create_app(tmp_path)
    with TestClient(app,base_url='http://127.0.0.1:8765') as c:
        c.headers['X-Local-Tool']='1'
        r=c.post('/api/selection/links',json={'urls':['https://item.taobao.com/item.htm?id=42'],'keyword':'链接分类'})
        assert r.status_code==200
        p=c.get('/api/products').json()['items'][0]
        assert p['keyword']=='链接分类' and p['detail_status']=='pending'
        assert not (tmp_path/'images').exists()
        assert c.post('/api/selection/browser/import',json={'urls':['https://item.taobao.com/item.htm?id=42']}).status_code==422
        assert c.post('/api/selection/links',json={'urls':['https://item.taobao.com/item.htm?id=43','https://evil.com/item?id=1']}).status_code==422
        assert c.get('/api/products').json()['total']==1

def test_link_only_item_gets_cover_after_details(tmp_path):
    from webapp.store import Store
    from webapp.selection import import_links
    store=Store(tmp_path)
    pid=import_links(store,['https://www.goofish.com/item?id=42'],'k')[0]
    product=store.selected([pid])[0]
    product.update(title='真实商品',gallery=['https://img.alicdn.com/a','https://img.alicdn.com/b'])
    store.upsert(product,'k')
    main=store.gallery(pid)[0]
    assert main['kind']=='main'
    assert store.selected([pid])[0]['image_url']=='https://img.alicdn.com/a'
    store.gallery_result(main['id'],'images/a.jpg',None)
    assert store.selected([pid])[0]['image_path']=='images/a.jpg'

def test_picker_login_state_is_saved_privately(tmp_path):
    from webapp.picker import save_login
    class Context:
        pages=[]
        def cookies(self): return [{'name':'unb','value':'private-value','domain':'.taobao.com','expires':-1}]
        def storage_state(self,path):
            from pathlib import Path
            Path(path).write_text('{"cookies":[]}',encoding='utf-8')
    assert save_login(Context(),'taobao',tmp_path)
    assert (tmp_path/'state'/'taobao_state.json').exists()

def test_picker_rejects_expired_or_wrong_domain_login(tmp_path):
    from webapp.picker import save_login
    class Context:
        pages=[]
        def cookies(self): return [{'name':'unb','value':'private','domain':'.evil.com','expires':-1},{'name':'unb','value':'old','domain':'.taobao.com','expires':1}]
    assert not save_login(Context(),'taobao',tmp_path)
    assert not (tmp_path/'state').exists()

def test_shop_navigation_during_scroll_keeps_original_source():
    from webapp.picker import discover
    class Links:
        def evaluate_all(self,script):
            return [{'url':'https://www.goofish.com/item?id=42','title':'原店商品','image_url':None}]
    class Page:
        url='https://www.goofish.com/personal?userId=1'
        def title(self): return '原店铺'
        def locator(self,selector): return Links()
        @property
        def mouse(self): return self
        def wheel(self,*args): self.url='https://www.goofish.com/personal?userId=2'
        def wait_for_timeout(self,ms): return None
    updates=[]
    with pytest.raises(ValueError,match='页面发生切换'):
        discover(Page(),'xianyu',2,100,lambda items,rounds:updates.append(items))
    assert updates[-1][0]['source_url']=='https://www.goofish.com/personal?userId=1'
    assert len(updates[-1])==1
