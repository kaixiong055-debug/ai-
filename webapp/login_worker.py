"""Run the existing helper, returning only allowlisted diagnostic codes."""
from __future__ import annotations
import json
import sys
from pathlib import Path
from typing import Callable

MESSAGES = {
    'saved': '已保存本地登录状态，平台有效性待采集验证',
    'saved_with_warning': '已保存本地登录状态，但后续处理异常；可尝试采集验证',
    'not_completed': '未检测到登录完成：可能等待超时或窗口提前关闭，请保持窗口打开等待自动保存',
    'encoding_error': '登录助手字符编码错误，请更新工具后重试',
    'file_error': '登录状态保存失败，请检查项目目录写入权限和磁盘空间',
    'browser_error': '浏览器操作失败：可能窗口提前关闭、页面加载失败或 Chromium 未安装，请重新打开登录窗口',
    'unexpected_error': '登录助手异常退出，请更新工具并重试',
}


def fingerprint(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size
    except OSError:
        return None


def run_login(login: Callable[[], bool], state: Path) -> str:
    before = fingerprint(state)
    try:
        ok = login()
        code = 'saved' if ok and fingerprint(state) is not None else 'not_completed'
    except UnicodeError:
        code = 'encoding_error'
    except OSError:
        code = 'file_error'
    except Exception as exc:
        # Never return exception strings: browser errors can contain session URLs.
        code = 'browser_error' if type(exc).__module__.startswith('playwright.') else 'unexpected_error'
    after = fingerprint(state)
    if code != 'saved' and after is not None and after != before:
        code = 'saved_with_warning'
    return code


def main() -> int:
    from scripts.login_helper import do_login, STATE_DIR
    platform, report = sys.argv[1:3]
    code = run_login(lambda: do_login(platform), STATE_DIR / f'{platform}_state.json')
    target = Path(report)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps({'code':code},ensure_ascii=False),encoding='utf-8')
    temporary.replace(target)
    return 0 if code in ('saved','saved_with_warning') else 1


if __name__ == '__main__':
    raise SystemExit(main())
