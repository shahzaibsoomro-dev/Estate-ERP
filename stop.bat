@echo off
echo Stopping Haven Builders ERP server...
taskkill /F /FI "WINDOWTITLE eq Haven ERP Server*" >nul 2>nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5050') do taskkill /F /PID %%a >nul 2>nul
echo Server stopped.
pause
