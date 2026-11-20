@echo off
rem Bianmachang - backend installer (Windows + Python 3.10+)
cd /d "%~dp0"
setlocal

set "PY="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [ERROR] Python not found. Install Python 3.10+ and check "Add Python to PATH".
    pause
    exit /b 1
)

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10+ required. Please upgrade Python.
    pause
    exit /b 1
)

echo [1/2] Installing dependencies (fastapi / uvicorn / openai / python-dotenv) ...
%PY% -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo [ERROR] pip install failed. Try a mirror:
    echo   %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    pause
    exit /b 1
)

echo [2/2] Verifying imports ...
%PY% -c "import fastapi, uvicorn, openai, dotenv" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Import check failed. install.bat and run.bat may use different Python.
    pause
    exit /b 1
)

echo.
echo Done! Double-click run.bat, then open http://127.0.0.1:8000
echo Optional: copy .env.example to .env and fill MAAS_API_KEY for online mode.
echo Without a key the app runs in sample-replay mode automatically.
pause
exit /b 0
