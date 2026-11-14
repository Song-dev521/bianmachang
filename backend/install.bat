@echo off
rem ============================================================
rem  辩码场 - 一键安装脚本
rem  环境：Windows + Python 3.10+（命令 py 可用）
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"

echo [1/2] 安装后端依赖 fastapi / uvicorn / openai / python-dotenv ...
py -m pip install -r requirements.txt

if errorlevel 1 (
  echo.
  echo [失败] 依赖安装未成功，请检查网络或 Python 环境。
  pause
  exit /b 1
)

echo [2/2] 校验通过。
echo.
echo 安装完成！启动方式：双击 run.bat，然后浏览器打开 http://127.0.0.1:8000
echo （首次使用请先把 .env.example 复制为 .env 并填入模型服务 API Key；
echo   不配置也可运行，前端会自动进入"样例回放"模式完整演示。）
pause
