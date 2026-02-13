@echo off
echo ===========================================
echo NexusCtrl - RDP Persistence Tool (Windows)
echo ===========================================
echo.
echo This script will disconnect your RDP session but KEEP THE DESKTOP ACTIVE.
echo This allows the screenshot monitor to continue working while you are away.
echo.
echo [!] IMPORTANT: You must run this script AS ADMINISTRATOR.
echo.
pause

:: Get the current session ID for the logged-in user
set SESSION_ID=
for /f "tokens=3" %%i in ('query session %username% ^| findstr /i "Active"') do set SESSION_ID=%%i

if "%SESSION_ID%"=="" (
    echo.
    echo [!] Manual Check Required.
    echo Please find the ID number for the "Active" session in the list below:
    echo.
    query session
    echo.
    set /p SESSION_ID="Enter the Session ID number: "
)

if "%SESSION_ID%"=="" (
    echo.
    echo [ABORTED] No Session ID was entered.
    pause
    exit /b
)

echo.
echo Detaching session %SESSION_ID% to console...
tscon.exe %SESSION_ID% /dest:console

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Error code %errorlevel%. 
    echo Please make sure you right-clicked and chose "Run as Administrator".
) else (
    echo.
    echo SUCCESS! You can now check your website dashboard.
)

pause
