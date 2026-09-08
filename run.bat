@echo off
title Traffic Simulation Runner
echo ========================================================
echo   Traffic Simulation Runner
echo ========================================================
echo.
echo How would you like to run the application?
echo [1] Run with Local Frontend + Docker DB/Backend (Recommended)
echo [2] Run Full Stack in Docker (Backend + Frontend + DB)
echo.
set /p choice="Enter option (1 or 2, default 1): "
if "%choice%"=="" set choice=1

if "%choice%"=="2" (
    echo.
    echo Starting Full Stack via Docker Compose...
    start "Traffic Simulation (Docker)" cmd /c "docker compose up --build -d"
    echo Waiting for containers to initialize...
    timeout /t 6 /nobreak >nul
    echo Opening dashboard in browser...
    start http://localhost:80/
    goto finish
)

echo.
echo Checking for Docker daemon...
docker info >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Docker daemon active. Starting DB and backend services via Docker Compose...
    docker compose up -d backend
    echo Waiting for backend DB service on port 8000...
    timeout /t 3 /nobreak >nul
) else (
    echo [INFO] Docker not active; starting native backend with authoritative SQLite database...
    start "Traffic Backend (Native)" cmd /c "cd backend && .venv\Scripts\uvicorn src.main:app --reload --host 127.0.0.1 --port 8000"
    timeout /t 3 /nobreak >nul
)

echo.
echo Starting Frontend Dashboard (npm run dev)...
start "Traffic Frontend" cmd /c "cd frontend && npm run dev"

echo.
echo Waiting for servers to initialize...
timeout /t 3 /nobreak >nul

echo.
echo Opening visualization in browser...
start http://localhost:5173/

:finish
echo.
echo.
echo Done! Keep the spawned command prompt windows open.
echo To shut down native mode, close the spawned command windows.
echo To shut down docker services, run: docker compose down
echo.
pause
