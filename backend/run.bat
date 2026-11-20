@echo off
rem Bianmachang - backend launcher. Port is configured here.
cd /d "%~dp0"
setlocal
set "PORT=8000"

set "PY="
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [ERROR] Python not found. Run install.bat first.
    pause
    exit /b 1
)

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10+ required. Please upgrade Python.
    pause
    exit /b 1
)

%PY% -c "import uvicorn, fastapi" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Dependencies missing. Run install.bat first.
    pause
    exit /b 1
)

rem First run: create .env from template (replay mode works without an API key)
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo [info] .env created from template. Sample-replay mode active.
)

rem Detect port already in use
set "PID_OCCUPIED="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /C:":%PORT% " ^| findstr /C:"LISTENING"') do set "PID_OCCUPIED=%%p"
if defined PID_OCCUPIED (
    echo [ERROR] Port %PORT% already in use, PID=%PID_OCCUPIED%
    echo   Close it: taskkill /PID %PID_OCCUPIED% /F
    echo   Or change PORT at the top of this file.
    pause
    exit /b 1
)

echo [info] Starting server: http://127.0.0.1:%PORT%
start "" http://127.0.0.1:%PORT%
%PY% -m uvicorn main:app --host 127.0.0.1 --port %PORT%
if errorlevel 1 (
    echo.
    echo [ERROR] Server exited abnormally. Check output above.
    pause
    exit /b 1
)
exit /b 0
