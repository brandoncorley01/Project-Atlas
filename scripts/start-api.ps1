# Start FastAPI (single process - no --reload on Windows to avoid zombie listeners).
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lib\dev-ports.ps1"
. "$PSScriptRoot\lib\kill-port.ps1"

$root = Split-Path -Parent $PSScriptRoot
$apiDir = Join-Path $root "apps\api"
$devDir = Join-Path $root ".dev"
$pidFile = Join-Path $devDir "api.pid"

if (-not (Test-Path "$apiDir\.venv\Scripts\uvicorn.exe")) {
    Write-Host "ERROR: API venv missing. Run: cd apps\api; python -m venv .venv; .\.venv\Scripts\pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

$existing = Get-NetTCPConnection -LocalPort $AtlasApiPort -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Port $AtlasApiPort busy - freeing..." -ForegroundColor Yellow
    Stop-PortListener -Port $AtlasApiPort | Out-Null
    Start-Sleep -Seconds 2
    $existing = Get-NetTCPConnection -LocalPort $AtlasApiPort -State Listen -ErrorAction SilentlyContinue
}
if ($existing) {
    Write-Host "Port $AtlasApiPort still busy - run .\scripts\stop-dev.ps1 first" -ForegroundColor Yellow
    exit 1
}

New-Item -ItemType Directory -Force -Path $devDir | Out-Null

$reloadFlag = $env:ATLAS_API_RELOAD
$uvicornArgs = @(
    "app.main:app",
    "--host", "127.0.0.1",
    "--port", "$AtlasApiPort"
)
if ($reloadFlag -eq "1") {
    Write-Host "NOTE: ATLAS_API_RELOAD=1 - reload enabled (may stack zombies on Windows)"
    $uvicornArgs += @("--reload", "--reload-dir", "app")
}

Write-Host "Starting API on http://127.0.0.1:$AtlasApiPort ..."

$env:OPENBLAS_NUM_THREADS = "1"
$proc = Start-Process -FilePath "$apiDir\.venv\Scripts\uvicorn.exe" `
    -ArgumentList $uvicornArgs `
    -WorkingDirectory $apiDir `
    -WindowStyle Normal `
    -PassThru

$proc.Id | Out-File -FilePath $pidFile -Encoding ascii -Force

$healthUrl = "http://127.0.0.1:$AtlasApiPort/api/v1/health"
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) {
            $ready = $true
            break
        }
    } catch { }
}

if ($ready) {
    Write-Host "API ready: $healthUrl (PID $($proc.Id))" -ForegroundColor Green
    exit 0
}

Write-Host "API started (PID $($proc.Id)) but health check timed out - check the API window." -ForegroundColor Yellow
exit 1
