@echo off
title Haven Builders ERP — Server
cd /d "%~dp0"

echo.
echo  =================================================
echo    Haven Builders ERP — Starting Server
echo  =================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    where python3 >nul 2>nul
    if %errorlevel% neq 0 (
        echo  ERROR: Python is not installed or not in PATH.
        pause
        exit /b 1
    )
    set PYCMD=python3
) else (
    set PYCMD=python
)

echo  Checking dependencies...
%PYCMD% -m pip install -r requirements.txt --quiet

echo  Starting FastAPI backend on http://localhost:5050 ...
start /min "Haven ERP Server" %PYCMD% -m uvicorn backend.main:app --host 0.0.0.0 --port 5050

timeout /t 3 /nobreak >nul

set CHROME="C:\Program Files\Google\Chrome\Application\chrome.exe"
set CHROME2="C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
set EDGE="C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

if exist %CHROME% (
    start "" %CHROME% --app="http://localhost:5050" --window-size=1440,900
) else if exist %CHROME2% (
    start "" %CHROME2% --app="http://localhost:5050" --window-size=1440,900
) else if exist %EDGE% (
    start "" %EDGE% --app="http://localhost:5050" --window-size=1440,900
) else (
    start "" "http://localhost:5050"
)

echo.
echo  ERP is running at http://localhost:5050
echo  Close the "Haven ERP Server" window to stop.
echo.
timeout /t 5
