import pytest
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

@pytest.mark.parametrize('jsonp',[False,True])
@pytest.mark.parametrize('main_api',['mtop.taobao.pcdetail.data.get','mtop.taobao.detail.newversion.get'])
def test_taobao_browser_collects_lazy_description(jsonp,main_api,monkeypatch):
    from unittest.mock import Mock
    monkeypatch.setattr('webapp.taobao_details.time.monotonic',Mock(side_effect=[0,30]))
    from webapp.taobao_details import collect
    from urllib.parse import urlencode
    class Response:
        def __init__(self,api,payload):
            self.url='https://h5api.m.taobao.com/h5/'+api+'/1.0/?'+urlencode({'data':'{"id":"42"}'})
            self.payload=payload
        def json(self):
            if jsonp:raise ValueError('JSONP')
            return self.payload
        def text(self):
            import json
            return 'mtopjsonp1('+json.dumps(self.payload)+');'
    class EmptyLocator:
        @property
        def first(self): return self
        def count(self): return 0
    class Page:
        wheels=0
        url='https://item.taobao.com/item.htm?id=42'
        def evaluate(self,*args):return []
        def on(self,event,callback): self.callback=callback
        def goto(self,url,**kwargs):
            assert url==self.url
            self.callback(Response(main_api,{'data':{'item':{'itemId':'42','images':['//img.alicdn.com/main.jpg']}}}))
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

def test_taobao_jsonp_response_is_decoded_without_eval():
    from webapp.taobao_details import response_payload
    class Response:
        def json(self):raise ValueError('not JSON')
        def text(self):return 'mtopjsonp7({"data":{"item":{"itemId":"42","images":["//img.alicdn.com/a"]}}});'
    assert response_payload(Response())['data']['item']['itemId']=='42'
    class Invalid(Response):
        def text(self):return 'alert(document.cookie);'
    import pytest
    with pytest.raises(ValueError):response_payload(Invalid())


def test_taobao_failure_diagnostic_does_not_expose_response(monkeypatch):
    import webapp.taobao_details as adapter
    from unittest.mock import Mock
    response=Mock(url='https://h5api.m.taobao.com/h5/mtop.taobao.pcdetail.data.get/1.0/',status=200)
    response.json.return_value={'data':{'unknown':'private-account-value'}}
    page=Mock(url='https://item.taobao.com/item.htm?id=42')
    callbacks={}
    page.on.side_effect=lambda event,callback:callbacks.update({event:callback})
    page.goto.side_effect=lambda *a,**k:callbacks['response'](response)
    page.is_closed.return_value=False
    context=Mock();context.new_page.return_value=page
    monkeypatch.setattr(adapter.time,'monotonic',Mock(side_effect=[0,30]))
    result=adapter.collect(context,'42')
    assert result['detail_status']=='failed'
    assert '商品结构未匹配 1 次' in result['detail_error']
    assert 'private-account-value' not in str(result)
    page.close.assert_called_once()

@pytest.mark.parametrize('returned_id',['other',None])
def test_unknown_api_requires_explicit_matching_product_id(monkeypatch,returned_id):
    import webapp.taobao_details as adapter
    from unittest.mock import Mock
    from urllib.parse import urlencode
    response=Mock(url='https://h5api.m.taobao.com/h5/mtop.taobao.detail.newversion.get/1.0/?'+urlencode({'data':'{"id":"42"}'}),status=200)
    item={'images':['https://img.alicdn.com/not-confirmed']}
    if returned_id:item['itemId']=returned_id
    response.json.return_value={'data':{'item':item}}
    page=Mock(url='https://item.taobao.com/item.htm?id=42')
    callbacks={};page.on.side_effect=lambda e,cb:callbacks.update({e:cb})
    page.goto.side_effect=lambda *a,**k:callbacks['response'](response)
    page.is_closed.return_value=False
    context=Mock();context.new_page.return_value=page
    monkeypatch.setattr(adapter.time,'monotonic',Mock(side_effect=[0,30]))
    result=adapter.collect(context,'42')
    assert result['detail_status']=='failed' and not result.get('gallery')
    assert 'MTop 响应 1 次' in result['detail_error']
    assert '目标商品地址' in result['detail_error']

def test_collects_initial_product_without_any_mtop_response(monkeypatch):
    import webapp.taobao_details as adapter
    from unittest.mock import Mock
    page=Mock(url='https://item.taobao.com/item.htm?id=42')
    page.evaluate.return_value=[{'item':{'itemId':'42','title':'初始商品','images':['//img.alicdn.com/main']},'pcDescContent':'<p>商品介绍</p><img src="//img.alicdn.com/detail">'}]
    page.is_closed.return_value=False
    context=Mock();context.new_page.return_value=page
    monkeypatch.setattr(adapter.time,'monotonic',Mock(side_effect=[0,30]))
    result=adapter.collect(context,'42')
    assert result['detail_status']=='collected' and result['title']=='初始商品'
    assert result['description']=='商品介绍'
    assert result['image_kinds']['https://img.alicdn.com/detail']=='detail'
    page.close.assert_called_once()

def test_tmall_detail_preserves_original_host_and_strips_tracking(monkeypatch):
    import webapp.taobao_details as adapter
    from unittest.mock import Mock
    page=Mock(url='https://detail.tmall.com/item.htm?id=42')
    page.evaluate.return_value=[{'item':{'itemId':'42','images':['//img.alicdn.com/main']},'pcDescContent':'<img src="//img.alicdn.com/detail">'}]
    page.is_closed.return_value=False
    context=Mock();context.new_page.return_value=page
    monkeypatch.setattr(adapter.time,'monotonic',Mock(side_effect=[0,30]))
    result=adapter.collect(context,'42',url='https://detail.tmall.com/item.htm?id=42&from=cart&mi_id=private')
    assert result['detail_status']=='collected'
    assert page.goto.call_args.args[0]=='https://detail.tmall.com/item.htm?id=42'

@pytest.mark.parametrize('url',['https://detail.tmall.com/item.htm?id=43','https://evil.com/item.htm?id=42'])
def test_detail_rejects_mismatched_or_untrusted_original_url(url):
    from webapp.taobao_details import collect
    from unittest.mock import Mock
    context=Mock()
    with pytest.raises(ValueError):collect(context,'42',url=url)
    context.new_page.assert_not_called()

def test_missing_desktop_details_uses_same_url_in_mobile_context(monkeypatch):
    from unittest.mock import Mock
    import webapp.taobao_details as adapter
    context=Mock();mobile=context.browser.new_context.return_value
    desktop={'gallery':['main'],'image_kinds':{'main':'gallery'},'detail_status':'partial','detail_error':'缺详情','description':''}
    phone={'gallery':['desc'],'image_kinds':{'desc':'detail'},'detail_status':'collected','detail_error':None,'description':'手机详情'}
    collector=Mock(side_effect=[desktop,phone]);monkeypatch.setattr(adapter,'collect',collector)
    url='https://detail.tmall.com/item.htm?id=42'
    result=adapter.collect_product(context,'42',url)
    assert result['gallery']==['main','desc'] and result['detail_status']=='collected'
    assert collector.call_args_list[1].args==(mobile,'42')
    assert collector.call_args_list[1].kwargs['url']==url
    assert context.browser.new_context.call_args.kwargs['is_mobile'] is True
    mobile.close.assert_called_once()


def test_auth_required_does_not_try_mobile_as_a_bypass(monkeypatch):
    from unittest.mock import Mock
    import webapp.taobao_details as adapter
    context=Mock();result={'detail_status':'failed','auth_required':True,'detail_error':'需要登录'}
    monkeypatch.setattr(adapter,'collect',Mock(return_value=result))
    assert adapter.collect_product(context,'42')==result
    context.browser.new_context.assert_not_called()

def test_mobile_description_components_are_actual_detail_images():
    import json
    from webapp.taobao_details import description_fields
    images,text=description_fields({'wdescContent':json.dumps({'pages':[
        {'componentType':'image','content':'//img.alicdn.com/mobile.jpg'},
        {'componentType':'text','content':'<p>手机图文详情</p>'},
        {'componentType':'button','content':'//img.alicdn.com/not-detail.jpg'},
        {'componentType':'image','content':'javascript:alert(1)'}]})})
    assert images==['https://img.alicdn.com/mobile.jpg'] and text=='手机图文详情'
