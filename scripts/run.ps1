$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path -LiteralPath 'apps\web\dist\index.html')) {
    npm --prefix apps/web run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
}
$env:VELA_DEMO_MODE = '1'
.\.venv\Scripts\python.exe -m uvicorn services.app:app --host 127.0.0.1 --port 8000

