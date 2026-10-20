@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo [ERROR] .venv not found. Please run setup.cmd first.
  pause
  exit /b 1
)

"%PY%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
  echo [INFO] Installing web dependencies ...
  "%PY%" -m pip install --disable-pip-version-check -q -i https://pypi.tuna.tsinghua.edu.cn/simple fastapi uvicorn
  if errorlevel 1 (
    echo [ERROR] Failed to install web dependencies.
    pause
    exit /b 1
  )
)

rem If the port is already serving our app, just open the browser instead of failing.
"%PY%" -c "import socket,sys;s=socket.socket();s.settimeout(1);sys.exit(0 if s.connect_ex(('127.0.0.1',8000))==0 else 1)"
if not errorlevel 1 (
  echo [INFO] The service is already running at http://127.0.0.1:8000
  echo [INFO] Opening browser ...
  start "" http://127.0.0.1:8000/
  timeout /t 3 >nul
  exit /b 0
)

echo [INFO] Starting at http://127.0.0.1:8000 ...
"%PY%" -X utf8 -m meeting_agent.api --host 127.0.0.1 --port 8000 --open

echo.
pause
