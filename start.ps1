[CmdletBinding()]
param (
    [switch]$Docker
)

$ErrorActionPreference = "Stop"

# Refresh PATH from registry so node/npm, python, and docker are always resolved
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    $python = "python"
}

function Test-PortInUse([int] $port) {
    return $null -ne (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Test-BackendHealthy() {
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 2 -ErrorAction SilentlyContinue
        return ($response.status -eq "healthy")
    } catch {
        return $false
    }
}

Write-Host "========================================================"
Write-Host "  Traffic Simulation - Application Startup"
Write-Host "========================================================"

# Check if Backend/DB is already running and responsive
$backendReady = Test-BackendHealthy()

if ($backendReady) {
    Write-Host "[OK] Backend & Database storage already active on port 8000"
} else {
    # Check if Docker is available
    $dockerAvailable = $false
    try {
        docker info >$null 2>&1
        if ($LASTEXITCODE -eq 0) {
            $dockerAvailable = $true
        }
    } catch {}

    if ($dockerAvailable) {
        Write-Host "Starting Docker database & backend services (docker compose up -d)..."
        docker compose up -d backend
        
        Write-Host "Waiting for backend database service to become healthy..."
        $attempts = 0
        while ($attempts -lt 15) {
            Start-Sleep -Seconds 1
            if (Test-BackendHealthy) {
                $backendReady = $true
                break
            }
            $attempts++
        }
        if ($backendReady) {
            Write-Host "[OK] Docker Backend & Database service initialized successfully."
        } else {
            Write-Host "[WARN] Docker backend did not respond in time; falling back to local runner."
        }
    } else {
        Write-Host "[INFO] Docker daemon not active or not installed; running backend locally."
    }

    # Fallback to local native backend if Docker did not take port 8000
    if (-not $backendReady) {
        if (Test-PortInUse 8000) {
            Write-Host "Port 8000 in use; assuming backend is running."
        } else {
            Write-Host "Starting native backend with authoritative local SQLite database..."
            Start-Process powershell.exe -WorkingDirectory $backend -ArgumentList @(
                "-NoExit",
                "-Command",
                "& '$python' -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000"
            )
            Start-Sleep -Seconds 2
        }
    }
}

# If user explicitly requested full Docker stack (including containerized frontend)
if ($Docker) {
    Write-Host "Ensuring full container stack is running..."
    docker compose up -d
    Write-Host "Frontend Dashboard: http://localhost"
    Write-Host "Backend API:        http://localhost:8000"
    Start-Sleep -Seconds 2
    Start-Process "http://localhost"
    exit 0
}

# Start local frontend development server if not already running
if (Test-PortInUse 5173) {
    Write-Host "[OK] Frontend dev server already running on port 5173"
} else {
    Write-Host "Starting frontend dev server..."
    Start-Process powershell.exe -WorkingDirectory $frontend -ArgumentList @(
        "-NoExit",
        "-Command",
        "npm run dev -- --host 0.0.0.0"
    )
}

Write-Host "--------------------------------------------------------"
Write-Host "Backend API:  http://localhost:8000"
Write-Host "Frontend App: http://localhost:5173"
Write-Host "--------------------------------------------------------"

Start-Sleep -Seconds 2
Start-Process "http://localhost:5173"
