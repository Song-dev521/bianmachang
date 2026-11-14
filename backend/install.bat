@echo off
rem ============================================================
rem  辩码场 - 后端依赖安装脚本（改进版）
rem  环境要求：Windows + Python 3.10 及以上
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
setlocal

rem ---------- 步骤 1：定位可用的 Python 解释器 ----------
set "PY="
rem 优先用 py 启动器，-3 保证选中 Python 3.x
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
rem 没有 py 启动器时回退到 PATH 里的 python
if not defined PY (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    echo [错误] 未找到可用的 Python 解释器。
    echo        请安装 Python 3.10+，安装时务必勾选 "Add Python to PATH"。
    echo        下载地址：https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

rem ---------- 步骤 2：校验 Python 版本 >= 3.10 ----------
rem 版本过低时 pydantic v2 / FastAPI 0.110+ 导入即失败，必须提前拦截
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if not errorlevel 1 goto :version_ok

rem 版本不达标：取出真实版本号用于提示（for 必须放在 if 块外，否则括号解析会被打断）
for /f "delims=" %%v in ('%PY% -c "import sys;print(sys.version.split()[0])"') do set "PYVER=%%v"
echo [错误] 当前 Python 版本为 %PYVER%，本项目要求 3.10 及以上。
echo        请升级 Python 后重新运行本脚本。
pause
exit /b 1

:version_ok

rem ---------- 步骤 3：安装依赖 ----------
echo [1/2] 正在安装后端依赖：fastapi / uvicorn / openai / python-dotenv ...
rem 不要用 >nul 吞掉输出，pip 的报错信息是排查问题的唯一线索
%PY% -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto :pip_failed

rem ---------- 步骤 4：导入自检 ----------
rem 只信 pip 返回码不够：可能装到了别的解释器，或者只装了一半
echo [2/2] 校验依赖是否可正常导入 ...
%PY% -c "import fastapi, uvicorn, openai, dotenv" >nul 2>&1
if errorlevel 1 goto :import_failed

echo.
echo 安装完成！启动方式：双击 run.bat，然后浏览器打开 http://127.0.0.1:8000
echo 首次使用请先把 .env.example 复制为 .env 并填入模型服务 API Key；
echo 不配置也可运行，前端会自动进入"样例回放"模式完整演示。
pause
exit /b 0

:pip_failed
rem pip 失败统一走这里：中文报错 + 暂停，避免窗口一闪而过
echo.
echo [错误] 依赖安装失败，pip 返回了非 0 退出码。
echo        可按下面顺序排查：
echo        1. 网络问题，换国内镜像重试：
echo           %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
echo        2. pip 自身损坏，修复 pip：
echo           %PY% -m ensurepip --upgrade
echo        3. 权限不足，改用 --user 参数，或以管理员身份运行本脚本
pause
exit /b 1

:import_failed
rem 装完了但导不进去，多半是解释器不一致
echo.
echo [错误] 依赖安装看似成功，但导入自检失败。
echo        常见原因：install.bat 与 run.bat 使用的不是同一套 Python 环境。
pause
exit /b 1