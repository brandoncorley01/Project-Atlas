# Auto-restart API when health checks fail (optional — off by default; use header Restart button).
$ErrorActionPreference = "SilentlyContinue"
. "$PSScriptRoot\lib\dev-ports.ps1"

$root = Split-Path -Parent $PSScriptRoot
$devDir = Join-Path $root ".dev"
$logFile = Join-Path $devDir "api-watchdog.log"
$lockFile = Join-Path $devDir "api-restarting.lock"
$cooldownFile = Join-Path $devDir "api-restart-cooldown.txt"
$healthUrl = "http://127.0.0.1:$AtlasApiPort/api/v1/health"
$intervalSec = 30
$failThreshold = 6
$cooldownSec = 180

New-Item -ItemType Directory -Force -Path $devDir | Out-Null

function Write-WatchdogLog {
    param([string]$Message)
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
    Add-Content -Path $logFile -Value $line -Encoding utf8
}

function Test-ApiHealth {
    try {
        $r = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 15
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

function In-Cooldown {
    if (-not (Test-Path $cooldownFile)) { return $false }
    try {
        $last = [datetime]::Parse((Get-Content $cooldownFile -Raw).Trim())
        return ((Get-Date) - $last).TotalSeconds -lt $cooldownSec
    } catch {
        return $false
    }
}

Write-WatchdogLog "watchdog started (port $AtlasApiPort, interval ${intervalSec}s, threshold $failThreshold)"

$failures = 0
while ($true) {
    if (Test-Path $lockFile) {
        $failures = 0
        Start-Sleep -Seconds $intervalSec
        continue
    }

    if (Test-ApiHealth) {
        if ($failures -gt 0) {
            Write-WatchdogLog "API recovered after $failures failed check(s)"
        }
        $failures = 0
    } else {
        $failures++
        Write-WatchdogLog "health check failed ($failures/$failThreshold)"
        if ($failures -ge $failThreshold -and -not (In-Cooldown)) {
            Write-WatchdogLog "restarting API (watchdog)..."
            (Get-Date).ToString("o") | Out-File -FilePath $cooldownFile -Encoding ascii -Force
            & "$PSScriptRoot\restart-api.ps1" | Out-Null
            $failures = 0
            Start-Sleep -Seconds 45
        }
    }
    Start-Sleep -Seconds $intervalSec
}
