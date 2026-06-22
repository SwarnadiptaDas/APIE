$ErrorActionPreference = "Continue"

# Resolve the project root relative to THIS script's location, regardless of CWD
$ProjectRoot = Resolve-Path "$PSScriptRoot\.."

Write-Host "==========================================="  -ForegroundColor Cyan
Write-Host "  Starting Autonomous Incident Engineer"      -ForegroundColor Cyan
Write-Host "==========================================="  -ForegroundColor Cyan
Write-Host "  Project Root: $ProjectRoot"                -ForegroundColor DarkGray

# Load .env variables
$envFile = Join-Path $ProjectRoot ".env"
$envExampleFile = Join-Path $ProjectRoot ".env.example"

if (Test-Path $envFile) {
    Write-Host "Loading environment variables from .env..." -ForegroundColor Green
    foreach($line in Get-Content $envFile) {
        if ($line -match '^\s*([^#][^=]+)=(.*)') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
} elseif (Test-Path $envExampleFile) {
    Write-Host "WARNING: .env not found. Falling back to .env.example..." -ForegroundColor Yellow
    foreach($line in Get-Content $envExampleFile) {
        if ($line -match '^\s*([^#][^=]+)=(.*)') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
} else {
    Write-Host "WARNING: No .env file found. Services may lack required API keys." -ForegroundColor Yellow
}

$PyPath = "C:\Users\smile\AppData\Local\Programs\Python\Python311\python.exe"
$NpmPath = "C:\Program Files\nodejs\npm.cmd"

# Define services to start (all paths are absolute via $ProjectRoot)
$services = @(
    @{
        Name       = "Telemetry Collector"
        Path       = Join-Path $ProjectRoot "services\telemetry-collector"
        InstallCmd = "& `"$PyPath`" -m pip install -r requirements.txt --quiet"
        RunCmd     = "`"$PyPath`" -m uvicorn main:app --host 0.0.0.0 --port 8001"
    },
    @{
        Name       = "Anomaly Detection"
        Path       = Join-Path $ProjectRoot "services\anomaly-detection"
        InstallCmd = "& `"$PyPath`" -m pip install -r requirements.txt --quiet"
        RunCmd     = "`"$PyPath`" main.py"
    },
    @{
        Name       = "AI Incident Agent"
        Path       = Join-Path $ProjectRoot "services\ai-incident-agent"
        InstallCmd = "& `"$PyPath`" -m pip install -r requirements.txt --quiet"
        RunCmd     = "`"$PyPath`" -m uvicorn main:app --host 0.0.0.0 --port 8000"
    },
    @{
        Name       = "React Dashboard"
        Path       = Join-Path $ProjectRoot "frontend"
        InstallCmd = "& `"$NpmPath`" install"
        RunCmd     = "`"$NpmPath`" run dev"
    }
)

$processes = @()

try {
    foreach ($service in $services) {
        Write-Host "`nStarting $($service.Name)..." -ForegroundColor Cyan
        Write-Host "  Path: $($service.Path)" -ForegroundColor DarkGray

        Push-Location $service.Path

        # Install dependencies
        Write-Host "  Installing dependencies..." -ForegroundColor Gray
        Invoke-Expression $service.InstallCmd

        # Start service in a new window so output is visible
        Write-Host "  Launching service..." -ForegroundColor Green
        $process = Start-Process -PassThru -FilePath "cmd.exe" `
            -ArgumentList "/k title $($service.Name) && $($service.RunCmd)" `
            -WorkingDirectory $service.Path
        $processes += $process

        Pop-Location

        # Small delay to let service start before the next one
        Start-Sleep -Seconds 2
    }

    Write-Host "`n===========================================" -ForegroundColor Green
    Write-Host "  All services started!" -ForegroundColor Green
    Write-Host "  Dashboard URL : http://localhost:5173"    -ForegroundColor Cyan
    Write-Host "  AI Agent API  : http://localhost:8000"    -ForegroundColor Cyan
    Write-Host "  Telemetry API : http://localhost:8001"    -ForegroundColor Cyan
    Write-Host "  Anomaly Svc   : http://localhost:8002"    -ForegroundColor Cyan
    Write-Host "==========================================="  -ForegroundColor Green
    Write-Host "  Close this window or press Ctrl+C to stop all services."
    Write-Host ""

    # Wait indefinitely
    while ($true) {
        Start-Sleep -Seconds 5
    }

} catch {
    Write-Host "An error occurred: $_" -ForegroundColor Red
} finally {
    Write-Host "Stopping all services..." -ForegroundColor Yellow
    foreach ($process in $processes) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    Write-Host "Services stopped." -ForegroundColor Green
}
