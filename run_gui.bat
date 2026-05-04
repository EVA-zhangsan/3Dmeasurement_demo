@echo off
REM ==============================================================================
REM 极简版高精度三维测量仪 - 工业级 GUI 启动脚本 v2.0
REM ==============================================================================
REM 功能：启动 PySide6 暗黑主题应用，采集激光位移传感器数据
REM 配置：40x40 栅格扫描 (1600 点), σ=2.5 高斯滤波, turbo colormap
REM ==============================================================================

setlocal enabledelayedexpansion

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║  工业级三维测量软件 v2.0 - Industrial Measurement System     ║
echo ║  Performance: 20x faster, Dark theme, Fail-safe design        ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

REM 设置项目路径
set PROJECT_DIR=%~dp0
set VENV_PYTHON=%PROJECT_DIR%.venv\Scripts\python.exe

REM 检查虚拟环境
if not exist "%VENV_PYTHON%" (
    echo [ERROR] 虚拟环境未找到: %VENV_PYTHON%
    echo.
    echo 请先运行:
    echo   python -m venv .venv
    echo   .\.venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM 检查依赖
echo [INFO] 检查依赖...
"%VENV_PYTHON%" -c "import data_source, gui" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] 缺少依赖，正在安装...
    call "%PROJECT_DIR%.venv\Scripts\pip" install -q -r "%PROJECT_DIR%requirements.txt"
)

REM 启动 GUI
echo [INFO] 启动 GUI 应用...
echo.
echo 快速操作指南:
echo   1. 点击 "开始测量" 采集 1600 点数据 (约 2 秒)
echo   2. 点击 "停止测量" 停止采集
echo   3. 点击 "刷新拟合" 生成 3D 曲面
echo   4. 点击 "导出图片" 保存暗黑背景 PNG
echo   5. 可选: "导入 CSV" 加载外部数据
echo.
echo 功能特性:
echo   ✓ 高性能: 0.001s/点, 每 100 点刷新一次
echo   ✓ 防呆设计: 测量期间自动禁用冲突按钮
echo   ✓ 暗黑主题: #1a1a1a 背景 + #0FF 荧光青文字
echo   ✓ 工业配色: turbo colormap + 坐标轴标签
echo   ✓ 实时状态: 窗口下方状态栏动态反馈
echo.
echo ────────────────────────────────────────────────────────────────
echo 更多信息见: README.md, INDUSTRIAL_UI_COMPLETE.md, VERIFICATION.md
echo ────────────────────────────────────────────────────────────────
echo.

REM 运行应用
cd /d "%PROJECT_DIR%"
"%VENV_PYTHON%" gui.py
if errorlevel 1 (
    echo.
    echo [ERROR] 应用异常退出 (exit code: %ERRORLEVEL%)
    pause
    exit /b %ERRORLEVEL%
)

endlocal
