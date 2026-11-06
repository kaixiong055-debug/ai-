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

def test_detail_session_borrows_live_browser_and_releases_lease(tmp_path,monkeypatch):
    from webapp.detail_session import DetailSession
    from webapp.picker_session import PickerSession
    picker=PickerSession(tmp_path)
    picker.proc=Mock();picker.proc.poll.return_value=None
    picker.platform='taobao';picker.folder=tmp_path
    monkeypatch.setattr(picker,'status',lambda:{'status':'ready'})
    launch=Mock()
    session=DetailSession(tmp_path,'taobao',launch,picker)
    assert picker.leased and session.borrowed
    launch.assert_not_called()
    with pytest.raises(ValueError):picker.send({'action':'save_login'})
    session.close()
    assert not picker.leased
    picker.proc.kill.assert_not_called()
