[CmdletBinding()]
param (
    [switch]$Docker
)

$ErrorActionPreference = "Stop"

if ($Docker) {
    Write-Host "========================================================"
    Write-Host "  Starting Traffic Simulation Stack in Docker"
    Write-Host "========================================================"
    docker compose up --build -d
    Write-Host "Waiting for containers to become healthy..."
    Start-Sleep -Seconds 5
    Write-Host "Frontend Dashboard: http://localhost"
    Write-Host "Backend API:        http://localhost:8000"
    Start-Process "http://localhost"
    exit 0
}

# Refresh PATH from registry so node/npm and python are always resolved
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

if (Test-PortInUse 8000) {
    Write-Host "Backend already running on port 8000"
} else {
    Start-Process powershell.exe -WorkingDirectory $backend -ArgumentList @(
        "-NoExit",
        "-Command",
        "& '$python' -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000"
    )
}

if (Test-PortInUse 5173) {
    Write-Host "Frontend already running on port 5173"
} else {
    Start-Process powershell.exe -WorkingDirectory $frontend -ArgumentList @(
        "-NoExit",
        "-Command",
        "npm run dev -- --host 0.0.0.0"
    )
}

Write-Host "Backend:  http://localhost:8000"
Write-Host "Frontend: http://localhost:5173"

Start-Sleep -Seconds 2
Start-Process "http://localhost:5173"
