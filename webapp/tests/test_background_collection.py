"""List-first collection and invisible browser regression tests."""
import json
import logging
import sys
from contextlib import nullcontext
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from webapp import details, worker


@pytest.mark.parametrize('platform', ['taobao', 'xianyu'])
def test_search_only_collects_list_in_background(monkeypatch, tmp_path, platform):
    @dataclass
    class Product:
        platform: str
        item_id: str = '123'
        title: str = '列表商品'
    batch = Mock(return_value={'词': SimpleNamespace(success=True, products=[Product(platform)])})
    crawler = SimpleNamespace(log=logging.getLogger('test-list-worker'),
                              sync_playwright=lambda: nullcontext(object()), run_platform_batch=batch)
    monkeypatch.setitem(sys.modules, 'run_cpu_crawl_pw', crawler)
    enrich = Mock()
    monkeypatch.setattr(details, 'enrich', enrich)
    output = tmp_path/'result.json'
    monkeypatch.setattr(sys, 'argv', ['worker', platform, '词', '1', str(output)])
    assert worker.main() == 0
    result = json.loads(output.read_text(encoding='utf-8'))
    assert result['success'] and len(result['products']) == 1
    enrich.assert_not_called()
    assert batch.call_args.kwargs['headed'] is False
    # Absent status lets SQLite retain previously collected details on repeat searches.
    assert 'detail_status' not in result['products'][0]


@pytest.mark.parametrize('platform', ['taobao', 'xianyu'])
def test_explicit_details_run_without_visible_window(monkeypatch, platform):
    browser = Mock()
    launch = Mock(return_value=browser)
    monkeypatch.setattr(details, 'sync_playwright', lambda: nullcontext(SimpleNamespace(chromium=SimpleNamespace(launch=launch))))
    collector = Mock(return_value={'detail_status':'collected', 'description':'详情'})
    if platform == 'taobao':
        from webapp import taobao_details
        monkeypatch.setattr(taobao_details, 'collect', collector)
    else:
        monkeypatch.setattr(details, 'collect', collector)
    products = [{'item_id':'123'}]
    details.enrich(products, platform=platform)
    assert products[0]['description'] == '详情'
    assert launch.call_args.kwargs['headless'] is True
    browser.close.assert_called_once()
