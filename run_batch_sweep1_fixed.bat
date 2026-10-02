@echo off
rem Sweep re-run with the timing fix: combo_10x (control) vs sweep1_10x, 16 each, round-robin (32 games, ~55 min)
cd /d "%~dp0"
python -u bot_batch.py --only combo_10x --only sweep1_10x --runs 16 --keep-dota
echo.
echo Batch finished. Press a key to close.
pause >nul
