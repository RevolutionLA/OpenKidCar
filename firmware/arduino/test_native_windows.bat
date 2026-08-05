@echo off
REM ============================================================
REM Windows 下运行小脑 native 协议测试
REM 用法：双击本文件，或命令行执行 test_native_windows.bat
REM
REM 说明：
REM   1. native 编译需要 gcc/g++（MinGW），已通过 w64devkit 安装到
REM      %USERPROFILE%\w64devkit\w64devkit\bin
REM   2. 本脚本临时把该目录加入 PATH（不改动系统环境变量）
REM   3. 若你的 w64devkit 装在其他位置，请修改下面的 DEVKIT 路径
REM ============================================================

set "DEVKIT=%USERPROFILE%\w64devkit\w64devkit\bin"
if not exist "%DEVKIT%\gcc.exe" (
    echo [错误] 未找到 gcc.exe：%DEVKIT%
    echo 请从 https://github.com/skeeto/w64devkit/releases 下载 w64devkit
    echo 解压后确保 bin\gcc.exe 存在，再运行本脚本。
    pause
    exit /b 1
)

set "PATH=%DEVKIT%;%PATH%"
call "%USERPROFILE%\.platformio\penv\Scripts\pio.exe" test -e native
if errorlevel 1 (
    echo.
    echo [失败] native 测试未通过
    pause
    exit /b 1
)
echo.
echo [成功] 全部 native 测试通过 ✓
pause
