# start-frontend.ps1
# Starts the CRA dev server on port 3000 (default) after freeing that port.
# Clears a stale REACT_APP_API_URL from the parent shell so the app uses /api + proxy → :8001.
#
# Usage:
#   .\start-frontend.ps1           # port 3000
#   .\start-frontend.ps1 -Port 3001

param(
    [int]$Port = 3000
)

Write-Host "[start-frontend] Cleaning up zombie processes and freeing port $Port ..." -ForegroundColor Cyan

Remove-Item Env:REACT_APP_API_URL -ErrorAction SilentlyContinue
$env:PORT = "$Port"
$env:BROWSER = "none"  # don't auto-open browser on restart

# Kill ALL node.js processes (cleans up zombie React dev servers from previous sessions)
$nodeProcs = Get-Process | Where-Object { $_.ProcessName -eq "node" }
if ($nodeProcs.Count -gt 0) {
    Write-Host "[start-frontend] Killing $($nodeProcs.Count) Node processes..." -ForegroundColor Yellow
    $nodeProcs | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

# Kill anything still on the target port
$pidsToKill = @()
try {
    $netstat = netstat -ano | Select-String ":$Port\s"
    foreach ($line in $netstat) {
        $tokens = ($line.ToString() -split "\s+") | Where-Object { $_ -ne "" }
        $candidate = $tokens[-1]
        if ($candidate -match '^\d+$' -and [int]$candidate -ne 0) {
            $pidsToKill += [int]$candidate
        }
    }
} catch {
    Write-Host "[start-frontend] netstat scan failed: $_" -ForegroundColor Yellow
}

$pidsToKill = $pidsToKill | Sort-Object -Unique
foreach ($p in $pidsToKill) {
    try {
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        Write-Host "[start-frontend] Killed PID $p on port $Port" -ForegroundColor Yellow
    } catch { }
}

if ($pidsToKill.Count -gt 0) {
    Start-Sleep -Seconds 2
}

# Clear webpack cache for fast compile (optional, comment out if you want faster restarts)
$cacheDir = Join-Path $PSScriptRoot "frontend\node_modules\.cache"
if (Test-Path $cacheDir) {
    Remove-Item $cacheDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "[start-frontend] Cleared webpack cache" -ForegroundColor Cyan
}

Write-Host "[start-frontend] Starting React on http://localhost:$Port (API via /api → 127.0.0.1:8001) ..." -ForegroundColor Green
Set-Location -Path "$PSScriptRoot\frontend"
npm start
