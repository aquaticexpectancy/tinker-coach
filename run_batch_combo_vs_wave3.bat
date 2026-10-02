@echo off
rem 16 runs each of combo_10x and wave3_10x, round-robin (32 games)
cd /d "%~dp0"
python -u bot_batch.py --only combo_10x --only wave3_10x --runs 16 --keep-dota
echo.
echo Batch finished. Press a key to close.
pause >nul
