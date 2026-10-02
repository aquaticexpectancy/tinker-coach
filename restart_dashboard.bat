@echo off
rem Restart the batch dashboard (batch_web.py, port 8765): stop whatever holds the port, then start it again.
cd /d "%~dp0"
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r /c:":8765 .*LISTENING"') do taskkill /F /PID %%p
timeout /t 2 >nul
python -u batch_web.py
pause
