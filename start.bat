@echo off
chcp 65001 > nul

:: 检查是否以管理员身份运行
NET SESSION >nul 2>&1
if %errorlevel% neq 0 (
    echo 请求管理员权限...
    powershell -Command "Start-Process cmd -Verb RunAs -ArgumentList '/c \"%~dp0start.bat\"'"
    exit /b 0
)

:: 切换到脚本所在目录
cd /d "%~dp0"

echo 正在检查Python环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python 未安装。请访问 https://www.python.org/downloads/ 安装 Python。
    pause
    exit /b 1
) else (
    echo Python 已安装。版本:
    python --version
)

echo 正在检查pip...
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo pip 未安装。请尝试运行 'python -m ensurepip' 或访问 https://pip.pypa.io/en/stable/installation/ 安装 pip。
    pause
    exit /b 1
) else (
    echo pip 已安装。版本:
    pip --version
)

echo 正在安装或更新依赖...
pip install --upgrade wheel
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo 依赖安装失败。请检查您的网络连接或requirements.txt文件。
    pause
    exit /b 1
)
echo 依赖完成
echo 正在启动F10截图工具...
python gui_app.py
