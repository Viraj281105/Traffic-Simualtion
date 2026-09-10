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
    }
    catch {
        return $false
    }
}

Write-Host "========================================================"
Write-Host "  Traffic Simulation - Application Startup"
Write-Host "========================================================"

# ---------------------------------------------------------------------
# DOCKER mode: full production-style container stack, nothing native.
# ---------------------------------------------------------------------
if ($Docker) {
    Write-Host "Starting full Docker stack (docker compose up -d)..."
    docker compose up -d

    Write-Host "--------------------------------------------------------"
    Write-Host "Frontend Dashboard: http://localhost"
    Write-Host "Backend API:        internal to the Docker network only"
    Write-Host "                    (proxied by nginx at /api, /ws, /health"
    Write-Host "                    - not published on localhost:8000)"
    Write-Host "--------------------------------------------------------"

    Start-Sleep -Seconds 2
    Start-Process "http://localhost"
    exit 0
}

# ---------------------------------------------------------------------
# LOCAL mode (default): native backend + native frontend, no Docker.
# ---------------------------------------------------------------------
if (Test-BackendHealthy) {
    Write-Host "[OK] Backend already running on port 8000"
}
else {
    if (Test-PortInUse 8000) {
        Write-Host "Port 8000 in use; assuming backend is running."
    }
    else {
        Write-Host "Starting native backend with local SQLite database..."
        Start-Process powershell.exe -WorkingDirectory $backend -ArgumentList @(
            "-NoExit",
            "-Command",
            "& '$python' -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000"
        )
        Start-Sleep -Seconds 2
    }
}

if (Test-PortInUse 5173) {
    Write-Host "[OK] Frontend dev server already running on port 5173"
}
else {
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
