@echo off
chcp 65001 > nul

echo 检查 Python 和 pip 环境...

rem 检查 Python 是否安装
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误：未找到 Python。请确保已安装 Python 并将其添加到 PATH 环境变量中。
    echo 建议从 https://www.python.org/downloads/ 下载并安装。
    pause
    exit /b 1
)

rem 检查 pip 是否安装
where pip >nul 2>&1
if %errorlevel% neq 0 (
    echo 未找到 pip，正在尝试安装 pip...
    python -m ensurepip --default-pip
    if %errorlevel% neq 0 (
        echo 错误：pip 安装失败。请手动安装 pip 或检查网络连接。
        pause
        exit /b 1
    ) else (
        echo pip 安装成功。
    )
) else (
    echo pip 已安装，版本信息：
    pip --version
)

echo 正在安装或更新依赖...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo 错误：依赖安装失败。请检查 requirements.txt 文件或网络连接。
    pause
    exit /b 1
)
echo 依赖安装完成。

echo 正在启动F12截图工具...
start "" python main.py
exit
