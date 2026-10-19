@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
set "PY=%~dp0.venv\Scripts\python.exe"

if not exist "%PY%" (
  echo [ERROR] .venv not found. Please run setup.cmd first.
  if /i not "%MA_NO_PAUSE%"=="1" pause
  exit /b 1
)

if not exist ".env" (
  echo [INFO] .env not found, creating from .env.example ...
  copy /y ".env.example" ".env" >nul
  echo [INFO] Please fill MEETING_AGENT_API_KEY in .env, save and close Notepad.
  start /wait notepad ".env"
)

"%PY%" -X utf8 -m meeting_agent.cli %*

echo.
if /i not "%MA_NO_PAUSE%"=="1" pause
