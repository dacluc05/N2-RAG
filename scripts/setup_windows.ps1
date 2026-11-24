$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$FinsightPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path $FinsightPython)) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
        throw 'Khong tim thay Python Launcher. Cai Python 3.12 x64 va bat Python Launcher.'
    }
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Khong tao duoc venv. Kiem tra py -0p.' }
}
& $FinsightPython -m pip install --index-url https://download.pytorch.org/whl/cpu torch
if ($LASTEXITCODE -ne 0) { throw 'Khong cai duoc PyTorch CPU.' }
& $FinsightPython -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Khong cai duoc dependencies.' }
& $FinsightPython -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency conflict.' }
if (-not (Test-Path '.env')) { Copy-Item '.env.example' '.env' }
Write-Host 'Dien .env, tao MySQL database/user theo README, sau do chay migrate va START_WINDOWS.bat.'

if (-not (Test-Path '.\frontend\web\dist\index.html')) {
    Write-Host 'Chua co ban dung React. Chay BUILD_WEB_WINDOWS.bat hoac START_WINDOWS.bat --legacy.'
}
