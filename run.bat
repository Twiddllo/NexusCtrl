@echo off
echo ===================================
echo NexusCtrl - Starting Services
echo ===================================

echo.
echo [1/3] Starting Backend API...
start "NexusCtrl Backend" cmd /k "uvicorn backend.app:app --reload --host 0.0.0.0"

echo.
echo [2/3] Starting Frontend Dashboard...
start "NexusCtrl Frontend" cmd /k "cd frontend && npm run dev"

echo.
echo [3/3] Starting Monitoring Agent...
start "NexusCtrl Agent" cmd /k "cd backend && python agent.py"

echo.
echo Services launched in separate windows.
echo Frontend: http://localhost:5173
echo Backend:  http://localhost:8000/api/docs
echo.
pause
