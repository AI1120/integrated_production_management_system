@echo off
setlocal
title IPMS Web
REM Start the IPMS web app on http://localhost:5173
cd /d "%~dp0frontend"

where npm >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm was not found on PATH.
    echo         Install Node.js 18 or newer, then open a NEW window and retry.
    goto :fail
)

if not exist "node_modules" (
    echo Installing dependencies...
    call npm install
    if errorlevel 1 goto :fail
)

echo.
echo IPMS web app starting on http://localhost:5173  (Ctrl+C to stop)
echo Start the backend too, with start-backend.cmd.
echo.
call npm run dev
if errorlevel 1 goto :fail
goto :eof

REM Without this the console closes the instant anything fails, and the user sees
REM a window flash with no readable error. vite.config.ts sets strictPort, so a
REM busy 5173 is now a hard failure rather than a silent hop to 5174 - which
REM makes surfacing the message mandatory, not optional.
:fail
echo.
echo *** The IPMS web app did not start (exit code %errorlevel%). The reason is above. ***
echo     Common causes:
echo       - "Port 5173 is already in use" ^(close the other IPMS window first^)
echo       - dependencies not installed ^(delete frontend\node_modules and retry^)
echo.
pause
exit /b 1
