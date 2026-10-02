@echo off
rem Smoke test of the new --sweep mode: 1 game each of sweep1_10x and sweep2_10x
cd /d "%~dp0"
python -u bot_batch.py --only sweep1_10x --only sweep2_10x --runs 1 --keep-dota
echo.
echo Smoke test finished. Press a key to close.
pause >nul
