# Quick API-only restart (use after editing Python code when reload is off).
$ErrorActionPreference = "SilentlyContinue"
. "$PSScriptRoot\lib\dev-ports.ps1"
. "$PSScriptRoot\lib\kill-port.ps1"

$root = Split-Path -Parent $PSScriptRoot
$devDir = Join-Path $root ".dev"
$lockFile = Join-Path $devDir "api-restarting.lock"
New-Item -ItemType Directory -Force -Path $devDir | Out-Null
(Get-Date).ToString("o") | Out-File -FilePath $lockFile -Encoding ascii -Force

Write-Host "Restarting API on port $AtlasApiPort ..."

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*$root*" -and $_.CommandLine -match "uvicorn" } |
    ForEach-Object { taskkill /F /T /PID $_.ProcessId 2>$null | Out-Null }

foreach ($port in @($AtlasApiPort) + $AtlasLegacyApiPorts) {
    $killed = Stop-PortListener -Port $port
    if ($killed -gt 0) {
        Write-Host "  Freed port $port ($killed listener(s))"
    }
}

Start-Sleep -Seconds 2

& "$PSScriptRoot\start-api.ps1"
$code = $LASTEXITCODE
Remove-Item $lockFile -Force -ErrorAction SilentlyContinue
exit $code
