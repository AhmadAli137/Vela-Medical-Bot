$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
New-Item -ItemType Directory -Force -Path '.cache' | Out-Null
$env:TEMP = Join-Path (Get-Location) '.cache'
$env:TMP = $env:TEMP
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
}
if (Get-Command uv -ErrorAction SilentlyContinue) {
    uv pip install --python .venv\Scripts\python.exe --cache-dir .cache\uv -r requirements.lock
} else {
    .\.venv\Scripts\python.exe -m pip install -r requirements.lock
}
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed' }
npm --prefix apps/web ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed' }
npm --prefix apps/web run build
if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
Write-Output 'Ready. Run .\scripts\run.ps1 and open http://127.0.0.1:8000'

