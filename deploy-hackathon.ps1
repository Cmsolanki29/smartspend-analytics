# SmartSpend hackathon deploy helper (run AFTER you create Neon DB)
# Usage:
#   .\deploy-hackathon.ps1
#   .\deploy-hackathon.ps1 -DatabaseUrl "postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require"

param(
    [string]$DatabaseUrl = ""
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Backend = Join-Path $Root "backend"

Write-Host "`n=== SmartSpend Hackathon Deploy Helper ===" -ForegroundColor Cyan

if (-not $DatabaseUrl) {
    Write-Host "`nPaste your Neon connection string (postgresql://...?sslmode=require):" -ForegroundColor Yellow
    $DatabaseUrl = Read-Host
}

if (-not $DatabaseUrl.Trim()) {
    Write-Host "ERROR: DATABASE_URL is required." -ForegroundColor Red
    exit 1
}

$env:DATABASE_URL = $DatabaseUrl.Trim()
Write-Host "`n[1/2] Applying migrations to Neon..." -ForegroundColor Green
Push-Location $Backend
try {
    python -m pip install -q -r requirements-render.txt 2>$null
    python -m scripts.apply_migrations
    if ($LASTEXITCODE -ne 0) { throw "Migrations failed (exit $LASTEXITCODE)" }

    Write-Host "`n[2/2] Seeding judge demo users (Pass@123)..." -ForegroundColor Green
    python -m scripts.seed_judge_demo_users
    if ($LASTEXITCODE -ne 0) { throw "Seed failed (exit $LASTEXITCODE)" }
}
finally {
    Pop-Location
}

Write-Host "`n=== DATABASE READY ===" -ForegroundColor Green
Write-Host @"

Next: Render (https://render.com)
  1. New + -> Blueprint -> repo: Cmsolanki29/smartspend-analytics
  2. Set env vars:
     DATABASE_URL = (same Neon string you just used)
     GROQ_API_KEY = (from your .env)
     OPENAI_API_KEY = (from your .env)
     GEMINI_API_KEY = (from your .env)
     FRONTEND_URL = (leave empty until Vercel is done)
  3. After deploy, test: https://YOUR-SERVICE.onrender.com/health

Then: Vercel (you will do this)
  Root directory: frontend
  REACT_APP_API_URL = https://YOUR-SERVICE.onrender.com/api

Judge login:
  judgedemo2@judge.smartspend.example.com / Pass@123

"@ -ForegroundColor White
