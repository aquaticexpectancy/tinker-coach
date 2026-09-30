@echo off
cd /d "%~dp0"
rem Close Dota first: Steam only applies these launch options to a fresh start.
tasklist /FI "IMAGENAME eq dota2.exe" | find /I "dota2.exe" >nul && (echo Dota is running - close it first, then run this again. & pause & exit /b)
tasklist /FI "IMAGENAME eq pythonw.exe" | find /I "pythonw.exe" >nul || start "" pythonw coach.py
python workshop.py play
