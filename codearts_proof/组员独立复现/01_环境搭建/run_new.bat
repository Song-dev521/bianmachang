@echo off
rem ============================================================
rem  服务启动脚本 run.bat
rem  重要：本文件必须保存为 UTF-8（不带 BOM）
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion

rem 端口集中在这里配置，被占用时改这一行即可
set "PORT=8000"
set "APP=main:app"

echo ============================================================
echo  步骤 1：环境自检
echo ============================================================

rem ---------- 1.1 源码是否就在脚本目录 ----------
if not exist "main.py" (
    echo [错误] 当前目录找不到 main.py
    echo        当前目录：%CD%
    echo        请把 run.bat 与源码放在同一目录后再运行。
    pause
    exit /b 1
)

rem ---------- 1.2 定位解释器：逻辑必须与 install.bat 完全一致 ----------
set "PY="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>&1
        if not errorlevel 1 set "PY=python"
    )
)
if not defined PY (
    echo [错误] 未找到 3.10 及以上的 Python。
    echo        请先双击 install.bat 完成环境准备。
    pause
    exit /b 1
)

rem ---------- 1.3 依赖是否完整 ----------
rem 提前拦截，避免 uvicorn 抛 ModuleNotFoundError 让用户看不懂
%PY% -c "import uvicorn, fastapi" >nul 2>&1
if errorlevel 1 (
    echo [错误] 依赖未安装完整，请先双击运行 install.bat。
    pause
    exit /b 1
)

rem ---------- 1.4 首次运行生成 .env ----------
rem copy 失败必须被发现，不能像旧版那样吞掉返回码还打印成功
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul 2>&1
        if errorlevel 1 (
            echo [警告] 生成 .env 失败，将使用默认配置（样例回放模式）。
        ) else (
            echo [info] 已从 .env.example 生成 .env（样例回放模式，无需 API Key）。
        )
    ) else (
        echo [警告] 未找到 .env.example，跳过 .env 生成。
    )
)

rem ---------- 2. 启动前检查端口占用 ----------
rem -p TCP 只取 TCP 连接，排除 UDP 干扰
rem ":8000 " 带尾随空格精确匹配本地地址列，避免把 18000 / 80000 误判为占用
rem 只统计 LISTENING 行，PID 是第 5 列；多个进程监听同一端口时全部收集
set "PIDS="
for /f "tokens=5" %%p in ('netstat -ano -p TCP ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    set "PIDS=!PIDS!%%p "
)
if defined PIDS goto :port_busy

rem ---------- 3. 启动服务 ----------
echo [info] 服务地址：http://127.0.0.1:%PORT%
echo [info] 按 Ctrl+C 停止服务
%PY% -m uvicorn %APP% --host 127.0.0.1 --port %PORT%
rem 非 0 退出码保留窗口方便看报错；手动 Ctrl+C 也可能进入这里，可忽略
if errorlevel 1 (
    echo.
    echo [错误] 服务异常退出（若是手动 Ctrl+C 可以忽略本提示）。
    echo        请查看上方 uvicorn 的输出。
    pause
    exit /b 1
)
exit /b 0

:port_busy
echo.
echo [错误] 端口 %PORT% 已被占用，占用进程 PID：!PIDS!
echo.
rem 占用的往往是上一轮没关掉的 uvicorn / python 进程
echo        查看是哪个程序：       tasklist /FI "PID eq <上面的PID>"
echo        结束该进程（需管理员）：taskkill /PID <上面的PID> /F
echo        或把本脚本顶部的 PORT 改成其它端口（如 8001）。
pause
exit /b 1