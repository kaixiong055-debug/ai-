from unittest.mock import Mock
import pytest


def test_original_reuses_platform_browser(tmp_path,monkeypatch):
    from webapp.picker_session import PickerSession
    picker=PickerSession(tmp_path)
    picker.proc=Mock();picker.proc.poll.return_value=None;picker.platform='taobao'
    monkeypatch.setattr(picker,'send',Mock(return_value={'status':'busy'}))
    picker.open_product('https://item.taobao.com/item.htm?id=123')
    picker.send.assert_called_once_with({'action':'open_product','url':'https://item.taobao.com/item.htm?id=123'})
    with pytest.raises(ValueError):picker.open_product('https://evil.com/item?id=123')


def test_session_reuses_worker_for_multiple_items(tmp_path,monkeypatch):
    from webapp.detail_session import DetailSession
    import threading
    proc=Mock();proc.poll.return_value=None
    launch=Mock(return_value=proc)
    session=DetailSession(tmp_path,'taobao',launch)
    def response(path):
        from webapp.picker import write_json
        import json
        cmd=json.loads(path.read_text())
        write_json(path.parent/'result.json',{'request_id':cmd['id'],'result':{'detail_status':'collected'}})
    original=session.wait_result
    def wait(request_id,cancel):
        response(session.folder/'command.json')
        return original(request_id,cancel)
    monkeypatch.setattr(session,'wait_result',wait)
    assert session.collect('1',threading.Event())['detail_status']=='collected'
    assert session.collect('2',threading.Event())['detail_status']=='collected'
    assert launch.call_count==1
    monkeypatch.setattr('webapp.detail_session.terminate',Mock())
    session.close()

def test_detail_session_uses_background_worker_when_picker_open(tmp_path,monkeypatch):
    from webapp.detail_session import DetailSession
    from webapp.picker_session import PickerSession
    from pathlib import Path
    picker=PickerSession(tmp_path)
    picker.proc=Mock();picker.proc.poll.return_value=None
    picker.platform='taobao';picker.folder=tmp_path
    monkeypatch.setattr(picker,'status',lambda:{'status':'ready'})
    def send(command,internal=False):
        assert command['action']=='export_state' and internal
        Path(command['destination']).write_text('{"cookies":[],"origins":[]}')
    picker.send=Mock(side_effect=send)
    proc=Mock();proc.poll.return_value=None
    launch=Mock(return_value=proc)
    session=DetailSession(tmp_path,'taobao',launch,picker)
    assert session.proc is proc and session.proc is not picker.proc
    assert launch.call_count==1
    assert picker.leased
    picker.send.assert_called_once()
    session.close()
    assert not picker.leased
    picker.proc.wait.assert_not_called()
    picker.proc.kill.assert_not_called()

def test_state_snapshot_reads_existing_tabs_without_creating_helper_pages(tmp_path):
    from webapp.picker import capture_state
    import json
    existing=tmp_path/'state.json'
    existing.write_text(json.dumps({'origins':[{'origin':'https://login.taobao.com','localStorage':[{'name':'old','value':'retained'}]}]}))
    tab=Mock();tab.url='https://item.taobao.com/item.htm?id=123'
    tab.evaluate.return_value={'origin':'https://item.taobao.com','localStorage':[{'name':'session','value':'private'}]}
    context=Mock();context.pages=[tab];context.cookies.return_value=[{'name':'unb','value':'private'}]
    result=capture_state(context,existing)
    assert len(result['origins'])==2 and result['cookies']==context.cookies.return_value
    context.new_page.assert_not_called()
    context.storage_state.assert_not_called()

@pytest.mark.parametrize('mode,headless',[('background',True),('compatible',False)])
def test_worker_browser_mode_is_explicit(tmp_path,monkeypatch,mode,headless):
    import sys,json
    from contextlib import nullcontext
    from types import SimpleNamespace
    from webapp import detail_worker
    (tmp_path/'command.json').write_text(json.dumps({'id':'stop','action':'close'}))
    launch=Mock();browser=launch.return_value
    monkeypatch.setattr(detail_worker,'sync_playwright',lambda:nullcontext(SimpleNamespace(chromium=SimpleNamespace(launch=launch))))
    monkeypatch.setattr(sys,'argv',['worker',str(tmp_path),'xianyu',mode])
    assert detail_worker.main()==0
    assert launch.call_args.kwargs['headless'] is headless
    browser.close.assert_called_once()
