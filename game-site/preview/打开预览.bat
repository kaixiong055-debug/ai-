@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
    py -3 serve_preview.py
    if errorlevel 1 pause
    exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
    python serve_preview.py
    if errorlevel 1 pause
    exit /b
)
echo 未找到 Python 3。可先直接打开 games\14545\index.html，或安装 Python 3 后重试。
pause
