@echo off
echo ===================================
echo NexusCtrl - Environment Setup
echo ===================================

echo.
echo [1/2] Installing Backend Dependencies...
pip install -r backend/requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Python dependencies.
    pause
    exit /b %errorlevel%
)

echo.
echo [2/2] Installing Frontend Dependencies...
cd frontend
call npm install
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install Node.js dependencies.
    pause
    exit /b %errorlevel%
)
cd ..

echo.
echo ===================================
echo Setup Complete!
echo You can now run the app using run.bat
echo ===================================
pause
