# Free a TCP listen port on Windows (Get-NetTCPConnection + netstat fallback).
function Stop-PortListener {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $pids = New-Object System.Collections.Generic.HashSet[int]

    try {
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique |
            ForEach-Object { [void]$pids.Add([int]$_) }
    } catch { }

    try {
        $pattern = ":\s*$Port\s+.*LISTENING\s+(\d+)\s*$"
        netstat -ano | ForEach-Object {
            if ($_ -match $pattern) {
                [void]$pids.Add([int]$Matches[1])
            }
        }
    } catch { }

    foreach ($pid in $pids) {
        if ($pid -le 0) { continue }
        taskkill /F /T /PID $pid 2>$null | Out-Null
        Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    }

    return $pids.Count
}
