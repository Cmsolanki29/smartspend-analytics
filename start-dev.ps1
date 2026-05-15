# start-dev.ps1 — Kills ALL zombie processes, then starts backend + frontend clean.
# Usage: .\start-dev.ps1
#
# Run this any time the app feels slow, hangs, or shows timeout errors.

$root = $PSScriptRoot

Write-Host "" -ForegroundColor White
Write-Host "╔═════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║     SmartSpend — Full Clean Restart     ║" -ForegroundColor Cyan
Write-Host "╚═════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ── 1. Kill all zombie Node.js processes ──────────────────────────────────────
$nodeProcs = Get-Process | Where-Object { $_.ProcessName -eq "node" } -ErrorAction SilentlyContinue
if ($nodeProcs -and $nodeProcs.Count -gt 0) {
    Write-Host "[clean] Killing $($nodeProcs.Count) Node.js processes..." -ForegroundColor Yellow
    $nodeProcs | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
}

# ── 2. Kill all zombie Python processes (>200MB = uvicorn workers from old sessions) ─
$pythonZombies = Get-Process | Where-Object {
    ($_.ProcessName -like "*python*") -and ($_.WorkingSet -gt 150MB)
} -ErrorAction SilentlyContinue
if ($pythonZombies -and $pythonZombies.Count -gt 0) {
    Write-Host "[clean] Killing $($pythonZombies.Count) Python zombie(s)..." -ForegroundColor Yellow
    $pythonZombies | ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

# ── 3. Kill anything on ports 8001 and 3000 ───────────────────────────────────
foreach ($port in @(8765, 3000)) {
    $pids = (netstat -ano 2>$null | Select-String ":$port\s") |
        ForEach-Object { ($_ -split "\s+")[-1] } |
        Where-Object { $_ -match "^\d+$" } |
        Select-Object -Unique
    foreach ($p in $pids) {
        Stop-Process -Id ([int]$p) -Force -ErrorAction SilentlyContinue
    }
    if ($pids) { Write-Host "[clean] Freed port $port" -ForegroundColor Yellow }
}

Start-Sleep -Seconds 1

# ── 4. Clear webpack cache ────────────────────────────────────────────────────
$cacheDir = Join-Path $root "frontend\node_modules\.cache"
if (Test-Path $cacheDir) {
    Remove-Item $cacheDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "[clean] Webpack cache cleared" -ForegroundColor Cyan
}

# ── 5. Start Backend ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "[start-dev] Launching backend in new window..." -ForegroundColor Green
Start-Process powershell -WorkingDirectory $root -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "start-backend.ps1")
)

Write-Host "[start-dev] Waiting 15s for migrations + uvicorn to start..." -ForegroundColor Yellow
Start-Sleep -Seconds 15

# ── 6. Verify backend is alive ────────────────────────────────────────────────
$backendOk = $false
for ($i = 0; $i -lt 3; $i++) {
    try {
        $r = (Invoke-WebRequest "http://127.0.0.1:8765/health" -TimeoutSec 5 -UseBasicParsing).StatusCode
        if ($r -eq 200) { $backendOk = $true; break }
    } catch { }
    Start-Sleep -Seconds 5
}

if ($backendOk) {
    Write-Host "[start-dev] Backend is healthy!" -ForegroundColor Green
} else {
    Write-Host "[start-dev] WARNING: Backend not responding. Check the backend window for errors." -ForegroundColor Red
}

# ── 7. Start Frontend ─────────────────────────────────────────────────────────
Write-Host "[start-dev] Launching frontend in new window..." -ForegroundColor Green
Start-Process powershell -WorkingDirectory $root -ArgumentList @(
    "-NoExit", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $root "start-frontend.ps1")
)

Write-Host ""
Write-Host "╔═════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║  Backend:  http://127.0.0.1:8765        ║" -ForegroundColor Green
Write-Host "║  Frontend: http://localhost:3000         ║" -ForegroundColor Green
Write-Host "║  Wait ~30s for frontend compilation     ║" -ForegroundColor Green
Write-Host "╚═════════════════════════════════════════╝" -ForegroundColor Green
