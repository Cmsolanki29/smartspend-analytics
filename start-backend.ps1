# start-backend.ps1
# Kills any process listening on the backend port (default 8001) then starts
# uvicorn fresh with --reload. Stops the "zombie uvicorn worker on port 8000"
# problem from happening again.
#
# Usage:
#   .\start-backend.ps1            # uses port 8002 (must match frontend setupProxy / package.json "proxy")
#   .\start-backend.ps1 -Port 8000 # use a different port

param(
    [int]$Port = 8002,
    [switch]$Reload
)

if ($Port -eq 8001) {
    Write-Host '[start-backend] WARNING: Port 8001 is outdated. Use port 8002 for Purchase/Festival APIs.' -ForegroundColor Red
    Write-Host '[start-backend] Run: .\start-backend.ps1 -Port 8002' -ForegroundColor Yellow
}

# Stop stale backends on the other default port (avoids CRA proxy hitting old code on 8001).
foreach ($stalePort in @(8001, 8002)) {
    if ($stalePort -eq $Port) { continue }
    Write-Host "[start-backend] Freeing stale port $stalePort ..." -ForegroundColor Yellow
    try {
        $netstat = netstat -ano 2>$null | Select-String "LISTENING" | Select-String ":$stalePort\s"
        foreach ($line in $netstat) {
            $tokens = ($line.ToString() -split "\s+") | Where-Object { $_ -ne "" }
            $procId = $tokens[-1]
            if ($procId -match '^\d+$' -and [int]$procId -ne 0) {
                Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
            }
        }
    } catch { }
}

# 0) Stop every python process whose command line is uvicorn targeting this port
#    (netstat PIDs can be stale on Windows; this catches system Python + stray workers.)
Write-Host "[start-backend] Stopping uvicorn processes bound to port $Port (CIM scan)..." -ForegroundColor Cyan
try {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^python' -and
            $_.CommandLine -and
            ($_.CommandLine -match 'uvicorn') -and
            ($_.CommandLine -match ('--port[= ]\s*' + $Port + '(\s|$)'))
        } |
        ForEach-Object {
            Write-Host "[start-backend]   PID $($_.ProcessId) $($_.ExecutablePath)" -ForegroundColor Yellow
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
} catch {
    Write-Host "[start-backend] CIM uvicorn scan failed: $_" -ForegroundColor Yellow
}
Start-Sleep -Seconds 1

Write-Host "[start-backend] Looking for processes on port $Port ..." -ForegroundColor Cyan

# Collect all PIDs that are LISTENING on the given port.
$pidsToKill = @()
try {
    # Only LISTENING rows. Matching any line with ":8765" also hits ESTABLISHED clients
    # (e.g. CRA proxy → API) and kills the wrong PID (often the Node dev server).
    $netstat = netstat -ano | Select-String "LISTENING" | Select-String ":$Port\s"
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

$portFile = Join-Path $PSScriptRoot "frontend\.backend-port"
try {
    Set-Content -Path $portFile -Value "$Port" -Encoding ascii -NoNewline
    Write-Host "[start-backend] Wrote $portFile (frontend proxy will use port $Port)" -ForegroundColor Cyan
} catch {
    Write-Host "[start-backend] Could not write $portFile : $_" -ForegroundColor Yellow
}

Set-Location -Path "$PSScriptRoot\backend"
Write-Host "[start-backend] Clearing Python __pycache__ (avoid stale .pyc)..." -ForegroundColor Cyan
Get-ChildItem -Path . -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }

# Resolve venv from cwd (backend/) — avoids wrong path if $PSScriptRoot + `backend\.venv` is misjoined.
$venvPy = Join-Path (Get-Location) ".venv\Scripts\python.exe"
$py = if (Test-Path -LiteralPath $venvPy) { $venvPy } else { "python" }
Write-Host "[start-backend] Using Python: $py" -ForegroundColor Cyan

# ML warmup blocks HTTP for minutes on first boot — skip for fast local dev (set in .env for prod if needed).
if (-not $env:SMARTSPEND_SKIP_ML_WARMUP) {
    $env:SMARTSPEND_SKIP_ML_WARMUP = "1"
    Write-Host "[start-backend] SMARTSPEND_SKIP_ML_WARMUP=1 (API ready in seconds)" -ForegroundColor Cyan
}

Write-Host "[start-backend] Applying pending SQL migrations (e.g. OTP timestamptz)..." -ForegroundColor Cyan
& $py -m scripts.apply_migrations
if ($LASTEXITCODE -ne 0) {
    Write-Host "[start-backend] ERROR: migrations failed. From backend folder run: python -m scripts.apply_migrations" -ForegroundColor Red
    exit $LASTEXITCODE
}

# Ghost LISTENING rows on Windows can block the port while no process exists — try next port once.
$bindPort = $Port
$maxPortTry = 3
for ($try = 0; $try -lt $maxPortTry; $try++) {
    $probe = $bindPort + $try
    try {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $probe)
        $listener.Start()
        $listener.Stop()
        $bindPort = $probe
        break
    } catch {
        Write-Host "[start-backend] Port $probe appears blocked (ghost or in use). Trying $($probe + 1)..." -ForegroundColor Yellow
        $bindPort = $probe + 1
    }
}
if ($bindPort -ne $Port) {
    Write-Host "[start-backend] Using port $bindPort instead of $Port (update frontend proxy via .backend-port)" -ForegroundColor Yellow
    try {
        Set-Content -Path $portFile -Value "$bindPort" -Encoding ascii -NoNewline
    } catch { }
}

$uvicornArgs = @("main:app", "--host", "127.0.0.1", "--port", "$bindPort")
if ($Reload) {
    Write-Host "[start-backend] --reload enabled (may spawn zombie workers on Windows)" -ForegroundColor Yellow
    $uvicornArgs += "--reload"
} else {
    Write-Host "[start-backend] Single worker (no --reload) for stable local dev" -ForegroundColor Cyan
}

if (Test-Path -LiteralPath $venvPy) {
    & $venvPy -m uvicorn @uvicornArgs
} else {
    & $py -m uvicorn @uvicornArgs
}
