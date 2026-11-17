@echo off
rem ============================================================
rem  依赖安装脚本 install.bat
rem  要求：Windows + Python 3.10 及以上
rem  重要：本文件必须保存为 UTF-8（不带 BOM），否则 chcp 65001 下中文会乱码
rem ============================================================
chcp 65001 >nul
cd /d "%~dp0"
setlocal

rem ---------- 0.1 依赖清单是否存在 ----------
if not exist "requirements.txt" (
    echo [错误] 当前目录找不到 requirements.txt
    echo        当前目录：%CD%
    pause
    exit /b 1
)

rem ---------- 0.2 定位解释器：先过版本门槛，再认定 ----------
rem PY     = 最终选定的、版本满足 3.10 的解释器
rem PY_ANY = 找到但不一定满足版本的解释器，只用于给出准确报错
set "PY="
set "PY_ANY="

rem 优先 py 启动器：-3 只选 Python 3，再单独校验小版本是否 >= 3.10
py -3 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    set "PY_ANY=py -3"
    py -3 -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PY=py -3"
)

rem py 不可用或版本不够时，回退 PATH 中的 python
rem 先用 where 确认存在，避免命中 WindowsApps 应用别名而弹出 Microsoft Store
if not defined PY (
    where python >nul 2>&1
    if not errorlevel 1 (
        set "PY_ANY=python"
        python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>&1
        if not errorlevel 1 set "PY=python"
    )
)

rem 三种结局分开处理，避免"版本过低"被误报成"未安装"
if defined PY goto :python_ready
if defined PY_ANY goto :version_too_low
goto :python_missing

:version_too_low
rem for 放在分支里而不是 if 括号内，防止复合语句把括号解析打断
for /f "delims=" %%v in ('%PY_ANY% -c "import sys;print(sys.version.split()[0])"') do set "PYVER=%%v"
echo [错误] 当前 Python 版本为 %PYVER%，低于本项目要求的 3.10。
echo        请升级 Python 后重新运行本脚本。
pause
exit /b 1

:python_missing
echo [错误] 未找到任何可用的 Python 解释器。
echo        请安装 Python 3.10+，安装时务必勾选 "Add Python to PATH"。
echo        下载地址：https://www.python.org/downloads/windows/
pause
exit /b 1

:python_ready
echo [info] 使用解释器：%PY%
rem 打印真实可执行文件路径，便于和 run.bat 对照，排查"装到别的解释器"
%PY% -c "import sys; print('       ' + sys.executable)"

rem ---------- 0.3 pip 是否可用 ----------
%PY% -m pip --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 该解释器没有可用的 pip，请先修复：
    echo        %PY% -m ensurepip --upgrade
    pause
    exit /b 1
)

rem ---------- 1. 安装依赖 ----------
echo.
echo [1/2] 正在安装依赖：fastapi / uvicorn / openai / python-dotenv ...
rem 不要用 >nul 吞掉输出，pip 的报错信息是排查问题的唯一线索
rem --no-input 防止 pip 停在交互式输入上导致窗口看似卡死
%PY% -m pip install --disable-pip-version-check --no-input -r requirements.txt
if errorlevel 1 goto :pip_failed

rem ---------- 2. 导入自检 ----------
rem 只信 pip 返回码不够：可能装进别的解释器，也可能只装了一半
echo [2/2] 正在校验依赖能否导入 ...
%PY% -c "import fastapi, uvicorn, openai, dotenv" >nul 2>&1
if errorlevel 1 goto :import_failed

echo.
echo 安装完成！
echo   启动：双击 run.bat，浏览器打开 http://127.0.0.1:8000
echo   如需接入真实模型：把 .env.example 复制为 .env 并填写 API Key
pause
exit /b 0

:pip_failed
echo.
echo [错误] 依赖安装失败（pip 返回非 0 退出码）。
echo        请按顺序排查：
echo        1. 网络问题，换国内镜像重试：
echo           %PY% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
echo        2. pip 自身损坏，修复后重试：
echo           %PY% -m ensurepip --upgrade
echo        3. 权限不足（Python 装在 Program Files 下时需要管理员权限）：
echo           右键以管理员身份运行本脚本，或改用 --user 参数安装
pause
exit /b 1

:import_failed
echo.
echo [错误] 依赖安装看似成功，但导入自检失败。
echo        常见原因：install.bat 与 run.bat 用的不是同一套 Python。
echo        请执行 %PY% -c "import sys;print(sys.executable)" 核对路径。
pause
exit /b 1