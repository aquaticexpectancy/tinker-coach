"""Live progress bar for the replay collector (download -> parse -> delete). Ctrl+C to close."""
import os
import time

LOG = r"C:\Users\docky\AppData\Local\Temp\claude\C--Users-docky-Documents-tinker\b475f138-0667-4ae0-8fbe-5b506d536a40\scratchpad\data\collect_log.txt"
TOTAL = 105

while True:
    lines = open(LOG, encoding="utf-8", errors="replace").read().splitlines() if os.path.exists(LOG) else []
    ok = sum(1 for l in lines if "parsed" in l or "done before" in l)
    bad = sum(1 for l in lines if "failed" in l or "not a replay" in l)
    n = int(40 * (ok + bad) / TOTAL)
    print(f"\r[{'#' * n}{'-' * (40 - n)}] {ok + bad}/{TOTAL}  {ok} parsed, {bad} failed   ", end="", flush=True)
    if any("games parsed" in l for l in lines):
        print("\ndone")
        break
    time.sleep(2)
