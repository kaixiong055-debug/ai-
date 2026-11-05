@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (set "PYTHON=python") else (set "PYTHON=py -3")
%PYTHON% -c "import sys; assert sys.version_info >= (3,10)" >nul 2>nul
if errorlevel 1 (
 echo [错误] 请安装 Python 3.10 或更新版本，并勾选 Add Python to PATH。
 pause
 exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
 %PYTHON% -m venv .venv
 if errorlevel 1 goto failure
)
.venv\Scripts\python.exe -c "import fastapi, uvicorn, playwright, PIL" >nul 2>nul
if errorlevel 1 (
 echo 正在安装本地工具依赖，请保持网络连接...
 .venv\Scripts\python.exe -m pip install -r webapp\requirements.txt
 if errorlevel 1 goto failure
)
.venv\Scripts\python.exe -c "from playwright.sync_api import sync_playwright; from pathlib import Path; p=sync_playwright().start(); ok=Path(p.chromium.executable_path).is_file(); p.stop(); raise SystemExit(0 if ok else 1)" >nul 2>nul
if errorlevel 1 (
 echo 正在安装 Chromium 浏览器...
 .venv\Scripts\python.exe -m playwright install chromium
 if errorlevel 1 goto failure
)
echo 正在启动商品工作台，浏览器将自动打开。关闭本窗口会停止服务。
.venv\Scripts\python.exe -m webapp.launcher
if errorlevel 1 goto failure
exit /b 0
:failure
echo [错误] 启动失败。请查看上方错误，检查网络、Python、磁盘权限或 8765 端口占用。
pause
exit /b 1
