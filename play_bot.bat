@echo off
rem Tinker Jev bot: close Dota first. Installs the bot map, starts the Jev bridge (this window) and launches Dota.
cd /d "%~dp0"
python bot.py %*
pause
