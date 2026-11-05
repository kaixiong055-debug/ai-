"""Private crawl subprocess. Only sanitized result records cross the boundary."""
from __future__ import annotations
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

ERRORS = {'LoginRequiredError':'登录已失效，请打开登录窗口重新登录',
          'AntiSpiderError':'平台要求人工验证或限制访问，请在浏览器完成验证后重试',
          'NetworkError':'平台网络连接失败或超时', 'ParseError':'未能解析商品，平台页面可能变化'}


def main() -> int:
    import run_cpu_crawl_pw as crawler
    # Existing CLI is unchanged. Web invocation suppresses raw account logs and page dumps.
    for handler in list(crawler.log.handlers):
        crawler.log.removeHandler(handler)
        handler.close()
    crawler.log.addHandler(logging.NullHandler())
    crawler.log.propagate = False
    crawler.dump_debug = lambda *a, **k: Path('disabled')
    crawler._snapshot_page = lambda *a, **k: None
    platform, keyword, pages, output = sys.argv[1:5]
    result = {'success':False,'products':[],'error':'采集进程失败，请检查浏览器安装和平台访问'}
    try:
        with crawler.sync_playwright() as p:
            r = crawler.run_platform_batch(p,platform,[keyword],int(pages),headed=True)[keyword]
            result = {'success':r.success,'products':[asdict(x) for x in r.products],
                      'error':None if r.success else ERRORS.get(r.error_type,'采集失败，请检查浏览器安装、登录或网络限制')}
    except Exception:
        # Do not persist exception text: upstream errors can contain session-bearing URLs.
        result['error'] = '浏览器启动或采集失败，请检查 Chromium 安装及可视桌面环境'
    for product in result['products']:
        product['detail_status']='pending' if platform=='xianyu' else 'unsupported'
    def save_progress(index: int | None = None, product: dict | None = None) -> None:
        result['detail_completed']=index if index is not None else result.get('detail_completed',0)
        result['detail_total']=len(result['products']) if platform=='xianyu' else 0
        temporary=Path(output).with_suffix('.tmp')
        temporary.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
        temporary.replace(output)
    save_progress()
    if platform=='xianyu' and result['success'] and result['products']:
        from .details import enrich
        try:
            enrich(result['products'],save_progress)
        except Exception:
            for product in result['products']:
                if product.get('detail_status')=='pending':
                    product.update(detail_status='failed',detail_error='详情任务中断，保留搜索主图；请重试详情采集')
        save_progress()

    return 0

if __name__ == '__main__':
    raise SystemExit(main())
