"""Private headless detail context reused for the entire batch."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from .details import ROOT, collect_in_context
from .picker import write_json, save_login


def main() -> int:
    folder=Path(sys.argv[1]);platform=sys.argv[2]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        context=browser.new_context(storage_state=str(ROOT/'state'/f'{platform}_state.json'),locale='zh-CN')
        # Keep images/scripts/XHR available for lazy detail extraction; skip only nonessential media/fonts.
        context.route('**/*',lambda route:route.abort() if route.request.resource_type in ('media','font') else route.continue_())
        last=''
        try:
            while True:
                try:command=json.loads((folder/'command.json').read_text(encoding='utf-8'))
                except (OSError,ValueError):command={}
                if command.get('id') and command['id']!=last:
                    last=command['id']
                    if command['action']=='close':break
                    result=collect_in_context(context,platform,command['item_id'])
                    if not result.get('auth_required'):
                        try:save_login(context,platform)
                        except Exception:pass  # Never expose cookie-bearing exception text.
                    write_json(folder/'result.json',{'request_id':last,'result':result})
                # Pump browser events without a visible window.
                if context.pages:context.pages[0].wait_for_timeout(100)
                else:
                    import time
                    time.sleep(.1)
        finally:browser.close()
    return 0

if __name__=='__main__':raise SystemExit(main())
