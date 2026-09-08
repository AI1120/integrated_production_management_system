@echo off
setlocal
title IPMS API
REM Start the IPMS API on http://127.0.0.1:8010
cd /d "%~dp0backend"

where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found on PATH.
    echo         Install Python 3.10 or newer, then open a NEW window and retry.
    goto :fail
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto :fail
    echo Installing dependencies...
    .venv\Scripts\python.exe -m pip install -q -r requirements.txt
    if errorlevel 1 goto :fail
)

if not exist "ipms.db" (
    echo Seeding the sample factory...
    .venv\Scripts\python.exe -m app.seed
    if errorlevel 1 goto :fail
)

echo.
echo IPMS API starting on http://127.0.0.1:8010  (Ctrl+C to stop)
echo.
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
if errorlevel 1 goto :fail
goto :eof

REM Without this the console closes the instant anything fails, and the user sees
REM a window flash with no readable error - which is indistinguishable from
REM "nothing happened".
:fail
echo.
echo *** The IPMS backend did not start (exit code %errorlevel%). The reason is above. ***
echo     Common causes:
echo       - port 8010 already in use  ^(another IPMS window is open^)
echo       - dependencies not installed ^(delete backend\.venv and retry^)
echo.
pause
exit /b 1
