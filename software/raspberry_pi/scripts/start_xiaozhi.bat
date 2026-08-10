@echo off
REM 一键启动：数字孪生双端 + 小智桥接
REM 真车部署请设置 OPENKIDCAR_PASSWORD 环境变量（否则拒绝启动）
REM 本地开发测试可加 --dev-allow-no-password 临时放行
cd /d %~dp0\..
echo [1/2] 启动小智桥接 (8010)...
start "小智桥接" py-xiaozhi\.venv\Scripts\python.exe digital_twin\backend\xiaozhi_bridge.py 8010
timeout /t 3 /nobreak >nul
echo [2/2] 启动数字孪生 (8000/8001)...
echo 提示：真车部署前请先设置密码：set OPENKIDCAR_PASSWORD=你的密码
if "%OPENKIDCAR_PASSWORD%"=="" (
  echo 未检测到密码环境变量，本机开发用 --dev-allow-no-password 放行...
  .venv\Scripts\python.exe digital_twin\backend\twin_server.py 8000 8001 --dev-allow-no-password
) else (
  .venv\Scripts\python.exe digital_twin\backend\twin_server.py 8000 8001
)
