@echo off
rem Lane creeps first: combo_10x (control) vs sweep1_10x vs sweep2_10x, 16 each, round-robin (48 games, ~70 min)
cd /d "%~dp0"
python -u bot_batch.py --only combo_10x --only sweep1_10x --only sweep2_10x --runs 16 --keep-dota
echo.
echo Batch finished. Press a key to close.
pause >nul
