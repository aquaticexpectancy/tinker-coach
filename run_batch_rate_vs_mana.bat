@echo off
rem Batch: rate_mana vs rate (router "rate", mana marches vs immortal marches), 5 runs each, round-robin.
rem Launches and closes Dota for every run - leave the PC alone until it finishes (~55 min).
cd /d "%~dp0"
python bot_batch.py --only rate_mana --only rate --runs 5
pause
