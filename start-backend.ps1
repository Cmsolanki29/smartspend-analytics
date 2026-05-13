# start-backend.ps1
# Kills any process listening on the backend port (default 8001) then starts
# uvicorn fresh with --reload. Stops the "zombie uvicorn worker on port 8000"
# problem from happening again.
#
# Usage:
#   .\start-backend.ps1            # uses port 8001
#   .\start-backend.ps1 -Port 8000 # use a different port

param(
    [int]$Port = 8001
)

Write-Host "[start-backend] Looking for processes on port $Port ..." -ForegroundColor Cyan

# Collect all PIDs that are LISTENING on the given port.
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
    Write-Host "[start-backend] netstat scan failed: $_" -ForegroundColor Yellow
}

$pidsToKill = $pidsToKill | Sort-Object -Unique
foreach ($p in $pidsToKill) {
    try {
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        Write-Host "[start-backend] Killed PID $p on port $Port" -ForegroundColor Yellow
    } catch {
        # ignore: process may already be gone
    }
}

# Also kill any orphan Python/uvicorn processes consuming > 200MB (zombie workers)
$currentPid = $PID
Get-Process | Where-Object {
    ($_.ProcessName -like "*python*") -and
    ($_.WorkingSet -gt 200MB) -and
    ($_.Id -ne $currentPid)
} | ForEach-Object {
    Write-Host "[start-backend] Killing zombie Python PID $($_.Id) ($([int]($_.WorkingSet/1MB))MB)" -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}

if ($pidsToKill.Count -gt 0) {
    Start-Sleep -Seconds 2
}

# Kill zombie Node.js processes (> 50 node processes is abnormal)
$nodeCount = (Get-Process | Where-Object { $_.ProcessName -like "node" }).Count
if ($nodeCount -gt 10) {
    Write-Host "[start-backend] WARNING: $nodeCount Node processes detected. Consider running .\start-frontend.ps1 to clean them." -ForegroundColor Yellow
}

Write-Host "[start-backend] Starting uvicorn on http://127.0.0.1:$Port ..." -ForegroundColor Green
Set-Location -Path "$PSScriptRoot\backend"
Write-Host "[start-backend] Clearing Python __pycache__ (avoid stale .pyc)..." -ForegroundColor Cyan
Get-ChildItem -Path . -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }

$venvPy = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"
$py = if (Test-Path $venvPy) { $venvPy } else { "python" }

Write-Host "[start-backend] Applying pending SQL migrations (e.g. OTP timestamptz)..." -ForegroundColor Cyan
& $py -m scripts.apply_migrations
if ($LASTEXITCODE -ne 0) {
    Write-Host "[start-backend] ERROR: migrations failed. From backend folder run: python -m scripts.apply_migrations" -ForegroundColor Red
    exit $LASTEXITCODE
}

if (Test-Path $venvPy) {
    & $venvPy -m uvicorn main:app --host 127.0.0.1 --port $Port --reload
} else {
    uvicorn main:app --host 127.0.0.1 --port $Port --reload
}
