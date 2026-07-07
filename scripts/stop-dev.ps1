# Stop all Project Atlas dev servers (API + web) and free ports.
$ErrorActionPreference = "SilentlyContinue"
. "$PSScriptRoot\lib\dev-ports.ps1"
. "$PSScriptRoot\lib\kill-port.ps1"

$root = Split-Path -Parent $PSScriptRoot
$ports = @($AtlasApiPort, $AtlasWebPort) + $AtlasLegacyApiPorts

Write-Host "Stopping Project Atlas dev servers..."

function Stop-AtlasProcessTree {
    param([int]$ProcessId)
    if ($ProcessId -le 0) { return }
    taskkill /F /T /PID $ProcessId 2>$null | Out-Null
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

# 1) Kill by command line (Project Atlas uvicorn / next dev)
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
        $cmd = $_.CommandLine
        $cmd -and (
            ($cmd -like "*$root*" -and $cmd -match "uvicorn") -or
            ($cmd -like "*$root*apps\web*" -and $cmd -match "next dev") -or
            ($cmd -like "*$root*" -and $cmd -match "node.*next")
        )
    } |
    ForEach-Object {
        Write-Host "  Stopping PID $($_.ProcessId) ($($_.Name))"
        Stop-AtlasProcessTree -ProcessId $_.ProcessId
    }

# 2) Kill anything listening on dev ports
foreach ($port in $ports) {
    $killed = Stop-PortListener -Port $port
    if ($killed -gt 0) {
        Write-Host "  Freed port $port ($killed listener(s))"
    }
}

# 3) Remove stale PID files
$devDir = Join-Path $root ".dev"
if (Test-Path $devDir) {
    $watchdogPid = Get-Content "$devDir\watchdog.pid" -ErrorAction SilentlyContinue
    if ($watchdogPid) {
        Stop-Process -Id ([int]$watchdogPid) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item "$devDir\api.pid", "$devDir\web.pid", "$devDir\watchdog.pid" -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Seconds 2

$blocked = @()
foreach ($port in @($AtlasApiPort, $AtlasWebPort)) {
    $listeners = @()
    try {
        $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction Stop)
    } catch { }
    if ($listeners.Count -gt 0) {
        $blocked += $port
    }
}

if ($blocked.Count -gt 0) {
    Write-Host ""
    Write-Host "WARNING: Port(s) still in use: $($blocked -join ', ')" -ForegroundColor Yellow
    Write-Host "Close any leftover PowerShell windows running uvicorn/next, or reboot once."
    exit 1
}

Write-Host "All dev ports free."
exit 0
