@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup_windows.ps1 first.
  exit /b 1
)
if not exist ".env" (
  echo Copy .env.example to .env and fill your settings.
  exit /b 1
)
".venv\Scripts\python.exe" -m scripts.launch %*
exit /b %errorlevel%
