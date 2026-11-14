@echo off
rem ============================================================
rem  辩码场 - 后端启动脚本（改进版）
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
setlocal
rem 端口集中在这里配置，被占用时改这一行即可
set "PORT=8000"

rem ---------- 步骤 1：探测 Python，必须与 install.bat 保持一致 ----------
set "PY="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [错误] 未找到 Python 解释器，请先双击运行 install.bat。
    pause
    exit /b 1
)

rem 挡住低版本 Python，避免抛出看不懂的 ImportError
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [错误] Python 版本低于 3.10，请升级后重试。
    pause
    exit /b 1
)

rem 依赖缺失时给出明确指引，而不是让 uvicorn 报 ModuleNotFoundError
%PY% -c "import uvicorn, fastapi" >nul 2>&1
if errorlevel 1 (
    echo [错误] 依赖未安装完整，请先双击运行 install.bat。
    pause
    exit /b 1
)

rem ---------- 步骤 2：首次运行从模板生成 .env ----------
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [info] 已从 .env.example 生成 .env，当前为样例回放模式（无需 API Key）
)

rem ---------- 步骤 3：启动前检测 8000 端口占用 ----------
rem 用 ":8000 " 带尾随空格精确匹配本地地址列，避免把 80000 之类误判成占用
rem netstat 行格式：TCP 本地地址 外部地址 LISTENING PID，PID 是第 5 列
set "PID_OCCUPIED="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /C:":%PORT% " ^| findstr /C:"LISTENING"') do set "PID_OCCUPIED=%%p"
if defined PID_OCCUPIED goto :port_busy

rem ---------- 步骤 4：启动服务 ----------
echo [info] 服务启动中：http://127.0.0.1:%PORT%
%PY% -m uvicorn main:app --host 127.0.0.1 --port %PORT%
rem 启动失败时暂停，保留窗口方便查看报错
if errorlevel 1 (
    echo.
    echo [错误] 服务异常退出，请查看上方 uvicorn 输出。
    pause
    exit /b 1
)
exit /b 0

:port_busy
echo.
echo [错误] 端口 %PORT% 已被占用，占用进程 PID：%PID_OCCUPIED%
echo        查看该进程：tasklist /FI "PID eq %PID_OCCUPIED%"
echo        结束该进程：taskkill /PID %PID_OCCUPIED% /F
echo        或修改本脚本开头的 PORT 变量，改用其它端口。
pause
exit /b 1