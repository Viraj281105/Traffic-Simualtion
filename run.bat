@echo off
title Traffic Simulation Runner
echo ========================================================
echo   Traffic Simulation Runner
echo ========================================================
echo.
echo How would you like to run the application?
echo [1] Run Natively (Local Python Virtualenv + npm dev server)
echo [2] Run via Docker (Full Stack Containerized: Backend + Frontend + DB)
echo.
set /p choice="Enter option (1 or 2): "

if "%choice%"=="2" (
    echo.
    echo Starting Full Stack via Docker Compose...
    start "Traffic Simulation (Docker)" cmd /c "docker compose up --build"
    echo Waiting for containers to initialize...
    timeout /t 6 /nobreak >nul
    echo Opening dashboard in browser...
    start http://localhost:80/
    goto finish
)

echo.
echo Starting Backend Natively...
start "Traffic Backend (Native)" cmd /c "cd backend && .venv\Scripts\uvicorn src.main:app --host 127.0.0.1 --port 8000"

echo.
echo Starting Frontend Dashboard...
start "Traffic Frontend" cmd /c "cd frontend && npm run dev"

echo.
echo Waiting for servers to initialize...
timeout /t 4 /nobreak >nul

echo.
echo Opening visualization in browser...
start http://localhost:5173/

:finish
echo.
echo.
echo Done! Keep the spawned command prompt windows open.
echo To shut down native mode, close the spawned command windows.
echo To shut down docker mode, run: docker compose down
echo.
pause
