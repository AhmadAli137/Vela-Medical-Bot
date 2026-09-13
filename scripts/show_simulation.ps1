param([ValidateSet('simulation','workspace','native')][string]$View = 'simulation')
$ErrorActionPreference = 'Stop'
$velaRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $velaRoot
$velaPython = Join-Path $velaRoot '.venv\Scripts\python.exe'
foreach ($velaRequired in @($velaPython, 'assets\simulation\room.glb', 'assets\simulation\robot.glb', 'assets\simulation\phone.glb', 'assets\simulation\meal_box.glb')) {
    if (-not (Test-Path -LiteralPath $velaRequired)) {
        throw "Missing demo file: $velaRequired. See README.md for setup and visual asset generation."
    }
}
node apps/web/scripts/check-scene-sync.mjs --check-build local | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Output 'Updating the local app to match this workspace...'
    npm --prefix apps/web run build
    if ($LASTEXITCODE -ne 0) { throw 'Local app build failed. See the scene synchronization errors above.' }
}
function Get-VelaHealth {
    try { return Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2 }
    catch { return $null }
}
$velaHealth = Get-VelaHealth
if (-not $velaHealth) {
    New-Item -ItemType Directory -Force -Path 'artifacts' | Out-Null
    $env:VELA_DEMO_MODE = '1'
    $velaProcess = Start-Process -FilePath $velaPython -ArgumentList '-m','uvicorn','services.app:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $velaRoot -WindowStyle Hidden -RedirectStandardOutput 'artifacts/simulation-server.stdout.log' -RedirectStandardError 'artifacts/simulation-server.stderr.log' -PassThru
    $velaDeadline = (Get-Date).AddSeconds(15)
    do {
        Start-Sleep -Milliseconds 300
        $velaHealth = Get-VelaHealth
        if ($velaProcess.HasExited -and -not $velaHealth) { throw 'The local server did not start. See artifacts/simulation-server.stderr.log.' }
    } while (-not $velaHealth -and (Get-Date) -lt $velaDeadline)
}
if (-not $velaHealth -or $velaHealth.mode -ne 'mock' -or $velaHealth.demo_mode -ne $true -or $velaHealth.hardware_execution -ne $false) {
    throw 'A Vela mock-mode demo server is not available on port 8000. See README.md.'
}
$velaBackendRevision = & $velaPython -m services.workspace_revision
if ($LASTEXITCODE -ne 0 -or $velaHealth.backend_revision -ne $velaBackendRevision) {
    throw 'The server on port 8000 was started with older workspace code. Close that server and reopen this launcher to load the synchronized version.'
}
if ($View -eq 'native') {
    Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/session' -Method Post -ContentType 'application/json' -Body '{"role":"staff"}' -SessionVariable velaSession | Out-Null
    $velaNative = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/sim/viewer' -Method Post -ContentType 'application/json' -Body '{}' -WebSession $velaSession -TimeoutSec 60
    Write-Output "Native MuJoCo: $($velaNative.status). Shared with http://127.0.0.1:8000/#simulation"
} else {
    $velaUrl = if ($View -eq 'workspace') { 'http://127.0.0.1:8000/#staff' } else { 'http://127.0.0.1:8000/#simulation' }
    Start-Process $velaUrl
    Write-Output "Vela: $velaUrl"
}
