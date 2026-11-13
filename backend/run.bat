@echo off
cd /d "%~dp0"
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo [info] .env created from .env.example - running in replay mode (no API key)
)
echo [info] starting server at http://127.0.0.1:8000
python -m uvicorn main:app --host 127.0.0.1 --port 8000
