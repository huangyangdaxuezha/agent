@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv" (
  echo [1/2] Creating virtual environment ...
  python -m venv .venv
  if errorlevel 1 (
    echo.
    echo [ERROR] Cannot create venv: Python 3.10+ not found.
    echo Install from https://www.python.org/downloads/ and check "Add python.exe to PATH".
    pause
    exit /b 1
  )
) else (
  echo [1/2] Virtual environment already exists, skipped.
)

echo [2/2] Installing dependencies ...
".venv\Scripts\python.exe" -m pip install -e ".[dev]"
if errorlevel 1 (
  echo [INFO] PyPI unreachable, retrying with Tsinghua mirror ...
  ".venv\Scripts\python.exe" -m pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
)

echo.
echo Done. Double-click run.cmd to start.
pause
