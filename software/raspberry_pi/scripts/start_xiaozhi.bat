@echo off
REM 一键启动：数字孪生双端 + 小智桥接
cd /d %~dp0\..
echo [1/2] 启动小智桥接 (8010)...
start "小智桥接" py-xiaozhi\.venv\Scripts\python.exe digital_twin\backend\xiaozhi_bridge.py 8010
timeout /t 3 /nobreak >nul
echo [2/2] 启动数字孪生 (8000/8001)...
.venv\Scripts\python.exe digital_twin\backend\twin_server.py 8000 8001
