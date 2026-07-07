# Start Project Atlas API + web (always stops stale processes first).
$ErrorActionPreference = "Stop"
. "$PSScriptRoot\lib\dev-ports.ps1"

$root = Split-Path -Parent $PSScriptRoot

Write-Host "=== Project Atlas dev ===" -ForegroundColor Cyan
Write-Host ""

& "$PSScriptRoot\stop-dev.ps1"
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Could not free all ports. Fix the warning above, then re-run start-dev.ps1." -ForegroundColor Red
    exit 1
}

Write-Host ""
& "$PSScriptRoot\start-api.ps1"
if ($LASTEXITCODE -ne 0) {
    exit 1
}

Write-Host ""
Write-Host "Starting web on http://localhost:$AtlasWebPort ..."

$webDir = Join-Path $root "apps\web"
$devDir = Join-Path $root ".dev"
New-Item -ItemType Directory -Force -Path $devDir | Out-Null

$webProc = Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd '$webDir'; npm run dev -- --port $AtlasWebPort"
) -PassThru

$webProc.Id | Out-File -FilePath (Join-Path $devDir "web.pid") -Encoding ascii -Force

# Optional watchdog — disabled by default (header Restart button is preferred).
$watchdogPidFile = Join-Path $devDir "watchdog.pid"
$existingWatchdog = Get-Content $watchdogPidFile -ErrorAction SilentlyContinue
if ($existingWatchdog) {
    Stop-Process -Id ([int]$existingWatchdog) -Force -ErrorAction SilentlyContinue
}
if ($env:ATLAS_API_WATCHDOG -eq "1") {
    $watchdogProc = Start-Process powershell -ArgumentList @(
        "-WindowStyle", "Hidden",
        "-ExecutionPolicy", "Bypass",
        "-File", "$PSScriptRoot\api-watchdog.ps1"
    ) -PassThru
    $watchdogProc.Id | Out-File -FilePath $watchdogPidFile -Encoding ascii -Force
    Write-Host "API watchdog running (PID $($watchdogProc.Id))"
} else {
    Remove-Item $watchdogPidFile -Force -ErrorAction SilentlyContinue
    Write-Host "API watchdog off (tap Restart in the app header if API drops)"
}

Start-Sleep -Seconds 4

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  API:  http://127.0.0.1:$AtlasApiPort/api/v1/health"
Write-Host "  Web:  http://localhost:$AtlasWebPort"
Write-Host ""
Write-Host "After editing Python API code: .\scripts\restart-api.ps1"
Write-Host "If API drops on phone: tap Restart in the top-right header"
Write-Host "To stop everything:            .\scripts\stop-dev.ps1"
