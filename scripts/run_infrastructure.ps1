$ErrorActionPreference = "Stop"

Write-Host "===========================================" -ForegroundColor Cyan
Write-Host " Starting Infrastructure via Docker Compose" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan

# Check if Docker is running
try {
    docker info > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Docker is not running. Please start Docker Desktop." -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "ERROR: Docker is not installed or not in PATH." -ForegroundColor Red
    exit 1
}

# Run the databases and observability tools
Write-Host "Starting TimescaleDB, Weaviate, Redis, Jaeger, and Prometheus..." -ForegroundColor Green
docker-compose up -d timescaledb weaviate redis jaeger prometheus t2v-transformers

Write-Host "`nInfrastructure is up and running in Docker!" -ForegroundColor Green
Write-Host "You can now run '.\scripts\run_all_native.ps1' to start the application natively." -ForegroundColor Cyan
