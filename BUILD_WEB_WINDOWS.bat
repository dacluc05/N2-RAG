@echo off
setlocal
cd /d "%~dp0frontend\web"
where npm.cmd >nul 2>nul
if errorlevel 1 (
  echo Install Node.js 22.12+ or 24 LTS and add npm.cmd to PATH.
  exit /b 1
)
call npm.cmd ci --no-fund
if errorlevel 1 exit /b 1
call npm.cmd run build
exit /b %errorlevel%
