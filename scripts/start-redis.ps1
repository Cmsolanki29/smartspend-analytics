# Optional: start Redis for SmartSpend (Docker). FraudShield works without it.
$ErrorActionPreference = "Stop"
docker run -d --name smartspend-redis -p 6379:6379 redis:7-alpine
Write-Host "Redis started on localhost:6379 (container: smartspend-redis)"
Write-Host "Restart the backend to connect. FraudShield works without Redis using fallbacks."
