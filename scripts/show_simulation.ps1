$ErrorActionPreference = 'Stop'
$velaRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $velaRoot
$velaPython = Join-Path $velaRoot '.venv\Scripts\python.exe'
foreach ($velaRequired in @($velaPython, 'apps\web\dist\index.html', 'assets\simulation\room.glb', 'assets\simulation\robot.glb')) {
    if (-not (Test-Path -LiteralPath $velaRequired)) {
        throw "Missing demo file: $velaRequired. See README.md for setup and visual asset generation."
    }
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
if (-not $velaHealth -or $velaHealth.mode -ne 'mock' -or $velaHealth.hardware_execution -ne $false) {
    throw 'A Vela mock-mode demo server is not available on port 8000. See README.md.'
}
Start-Process 'http://127.0.0.1:8000/#simulation'
Write-Output 'Vela simulation: http://127.0.0.1:8000/#simulation'
