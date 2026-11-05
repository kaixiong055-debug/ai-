from pathlib import Path
from webapp.store import Store

def test_taobao_image_types():
    from webapp.taobao_details import parse_detail
    payload={'data':{'item':{'itemId':'42','images':['//img.alicdn.com/a.jpg']},'skuBase':{'props':[{'values':[{'image':'//img.alicdn.com/sku.jpg'}]}]},'pcDescContent':'<p>商品介绍</p><img src="//img.alicdn.com/detail.jpg">'}}
    r=parse_detail(payload,'42')
    assert r['gallery']==['https://img.alicdn.com/a.jpg','https://img.alicdn.com/sku.jpg','https://img.alicdn.com/detail.jpg']
    assert r['image_kinds'][r['gallery'][1]]=='sku'
    assert r['image_kinds'][r['gallery'][2]]=='detail'
    assert r['description']=='商品介绍'
    assert parse_detail(payload,'43') is None

def test_unrecognized_taobao_payload_not_success():
    from webapp.taobao_details import parse_detail
    assert parse_detail({'data':{'recommendations':[{'images':['https://img.alicdn.com/x']}] }},'42') is None

def test_gallery_type_persists_on_search_refresh(tmp_path: Path):
    store=Store(tmp_path)
    p={'platform':'taobao','item_id':'42','title':'商品','image_url':'https://img.alicdn.com/a','gallery':['https://img.alicdn.com/b'],'image_kinds':{'https://img.alicdn.com/b':'sku'}}
    pid=store.upsert(p,'k')
    store.upsert({k:v for k,v in p.items() if k not in ('gallery','image_kinds')},'k')
    assert store.gallery(pid)[1]['kind']=='sku'

def test_taobao_browser_collects_lazy_description():
    from webapp.taobao_details import collect
    from urllib.parse import urlencode
    class Response:
        def __init__(self,api,payload):
            self.url='https://h5api.m.taobao.com/h5/'+api+'/1.0/?'+urlencode({'data':'{"id":"42"}'})
            self.payload=payload
        def json(self): return self.payload
    class EmptyLocator:
        @property
        def first(self): return self
        def count(self): return 0
    class Page:
        wheels=0
        url='https://item.taobao.com/item.htm?id=42'
        def on(self,event,callback): self.callback=callback
        def goto(self,url,**kwargs):
            assert url==self.url
            self.callback(Response('mtop.taobao.pcdetail.data.get',{'data':{'item':{'itemId':'42','images':['//img.alicdn.com/main.jpg']}}}))
        def locator(self,selector): return EmptyLocator()
        @property
        def mouse(self): return self
        def wheel(self,*args):
            self.wheels+=1
            if self.wheels<5: return
            self.callback(Response('mtop.taobao.detail.getdesc',{'data':{'pcDescContent':'<img src="//img.alicdn.com/desc.jpg"><p>说明</p>'}}))
        def wait_for_timeout(self,n): return None
        def is_closed(self): return False
        def close(self): return None
    class Context:
        def new_page(self): return Page()
    r=collect(Context(),'42')
    assert r['detail_status']=='collected'
    assert r['image_kinds']['https://img.alicdn.com/desc.jpg']=='detail'
    assert r['description']=='说明'

def test_taobao_only_carousel_reports_partial():
    from webapp.taobao_details import parse_detail
    result=parse_detail({'data':{'item':{'itemId':'42','images':['https://img.alicdn.com/a']}}},'42')
    assert result['detail_status']=='partial' and result['detail_error']

def test_taobao_desc_excludes_script_content():
    from webapp.taobao_details import description_fields
    images,text=description_fields({'pcDescContent':'<script>secret</script><style>hidden</style><p>描述</p><img data-src="//img.alicdn.com/x"><img src="data:text/html,evil">'})
    assert text=='描述' and images==['https://img.alicdn.com/x']

def test_repeated_taobao_responses_keep_all_images():
    from webapp.taobao_details import merge_result
    rich={'gallery':['a','b'],'image_kinds':{'a':'gallery','b':'detail'},'description':'说明','detail_status':'collected','detail_error':None}
    sparse={'gallery':['a','c'],'image_kinds':{'a':'gallery','c':'sku'},'description':'','detail_status':'partial','detail_error':'无详情图'}
    merge_result(rich,sparse)
    assert rich['gallery']==['a','b','c']
    assert rich['description']=='说明'
    assert rich['detail_status']=='collected' and rich['detail_error'] is None
