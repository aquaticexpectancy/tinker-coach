"""Run several bot setups a few times each and compare their averages (single runs swing by ~±200 net worth).

    python bot_batch.py                  4 setups x 5 runs, round-robin (~90 min); Dota restarts between runs
    python bot_batch.py --runs 3         3 of each
    python bot_batch.py --only jev_aim   one setup (names below)
    python bot_batch.py --report         the latest batch's table again (or --report bot_runs/batch_<time>.csv)

Every run is the F11 drill start (5:00 in fountain) to 10:00 at 2x, no video. Leave the PC alone while it runs:
it launches and closes Dota each time. Ctrl+C stops after closing Dota; the runs so far stay in the batch file.
"""
from __future__ import annotations

import argparse
import csv
import glob
import json
import math
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "bot_runs")
SETUPS = {                                  # name: bot.py arguments
    "rules_facing": ["--advisor", "rules", "--route", "rules", "--aim", "off", "--ready", "old", "--router", "rules", "--marches", "immortal", "--tricks", "off", "--plan", "auto"],
    "rules_aim": ["--advisor", "rules", "--route", "rules", "--aim", "on", "--router", "rules", "--marches", "immortal", "--tricks", "off", "--plan", "auto"],
    "jev_facing": ["--advisor", "jev", "--route", "jev", "--aim", "off", "--tricks", "off", "--plan", "auto"],
    "jev_aim": ["--advisor", "jev", "--route", "jev", "--aim", "on", "--tricks", "off", "--plan", "auto"],
    "rules_mana": ["--advisor", "rules", "--route", "rules", "--aim", "off", "--marches", "mana", "--ready", "old", "--router", "rules", "--tricks", "off", "--plan", "auto"],
    "rules_fresh": ["--advisor", "rules", "--route", "rules", "--aim", "off", "--ready", "fresh", "--router", "rules", "--marches", "immortal", "--tricks", "off", "--plan", "auto"],
    "rate": ["--advisor", "rules", "--route", "rules", "--aim", "off", "--ready", "fresh", "--router", "rate", "--marches", "immortal", "--tricks", "off", "--plan", "auto"],
    "rate_mana": ["--advisor", "rules", "--route", "rules", "--aim", "off", "--ready", "fresh", "--router", "rate", "--marches", "mana", "--tricks", "off", "--plan", "auto"],
    "tricks": ["--advisor", "rules", "--route", "rules", "--aim", "off", "--ready", "fresh", "--router", "rate", "--marches", "mana", "--tricks", "on", "--plan", "auto"],
    "user": ["--advisor", "rules", "--route", "rules", "--aim", "off", "--ready", "fresh", "--router", "rate", "--marches", "mana", "--tricks", "on", "--plan", "user"],
    "lab": ["--advisor", "rules", "--route", "rules", "--aim", "off", "--ready", "fresh", "--router", "rate", "--marches", "mana", "--tricks", "on", "--plan", "lab"],
}
COMMON = ["--drill", "--speed", "2", "--no-video", "--no-hud"]   # follow a batch with lab_hud.py
TIMEOUT = 15 * 60                           # a run is ~4-5 min; anything past this is stuck
FIELDS = ["setup", "run", "status", "nw", "lh", "camp_trips", "camp_lh", "wave_trips", "wave_lh", "jev_lowconf", "jev_calls"]


def close_dota():
    subprocess.run(["taskkill", "/IM", "dota2.exe"], capture_output=True)
    for _ in range(30):
        if "dota2.exe" not in subprocess.run(["tasklist", "/FI", "IMAGENAME eq dota2.exe"],
                                             capture_output=True, text=True).stdout.lower():
            return
        time.sleep(1)
    subprocess.run(["taskkill", "/F", "/IM", "dota2.exe"], capture_output=True)
    time.sleep(3)


def run_stats(path: str) -> dict:
    rows = []
    for line in open(path, encoding="utf-8"):
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    end = next((r for r in reversed(rows) if r.get("kind") == "end"), None)
    trips = [r for r in rows if r.get("kind") == "trip"]
    camp = [t["last_hits"] for t in trips if t["station"] != "B"]
    wave = [t["last_hits"] for t in trips if t["station"] == "B"]
    jev = [r for r in rows if r.get("kind") == "jev" and r.get("question") == "station"]
    return {"status": "ok" if end else "no_end", "nw": end and end.get("nw"), "lh": end and end.get("lh"),
            "camp_trips": len(camp), "camp_lh": round(sum(camp) / len(camp), 2) if camp else None,
            "wave_trips": len(wave), "wave_lh": round(sum(wave) / len(wave), 2) if wave else None,
            "jev_calls": len(jev), "jev_lowconf": sum(r.get("confidence", 1) < 0.35 for r in jev)}


def one_run(setup: str) -> dict:
    close_dota()
    cmd = [sys.executable, "-u", os.path.join(HERE, "bot.py"), *SETUPS[setup], *COMMON]
    p = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    found = {}

    def read():
        for line in p.stdout:
            m = re.search(r"recording to (.+\.jsonl)", line)
            if m:
                found["path"] = m.group(1).strip()
            if "Traceback" in line or "Error" in line or "close it first" in line:
                print("   bot.py:", line.rstrip())
    th = threading.Thread(target=read, daemon=True)
    th.start()
    try:
        p.wait(timeout=TIMEOUT)
        status = None
    except subprocess.TimeoutExpired:
        p.kill()
        status = "timeout"
    th.join(5)
    close_dota()
    path = found.get("path")
    if not path or not os.path.exists(path):
        return {"setup": setup, "run": None, "status": status or "no_log"}
    st = run_stats(path)
    if status:
        st["status"] = status
    return {"setup": setup, "run": os.path.basename(path), **st}


def report(path: str):
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8")) if r["status"] == "ok"]
    by = {}
    for r in rows:
        by.setdefault(r["setup"], []).append(r)

    def ms(vals):
        vals = [float(v) for v in vals if v not in ("", None)]
        if not vals:
            return None, None, 0
        m = sum(vals) / len(vals)
        se = math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1) / len(vals)) if len(vals) > 1 else None
        return m, se, len(vals)

    print(f"\n{os.path.basename(path)}: {len(rows)} finished runs")
    print(f"  {'setup':14s} {'n':>2s}  {'net worth':>16s}  {'last hits':>12s}  {'LH/camp trip':>12s}  {'LH/wave':>7s}  range")
    base = None
    for name in SETUPS:
        g = by.get(name)
        if not g:
            continue
        nw, nse, n = ms(r["nw"] for r in g)
        lh, lse, _ = ms(r["lh"] for r in g)
        cl, _, _ = ms(r["camp_lh"] for r in g)
        wl, _, _ = ms(r["wave_lh"] for r in g)
        nws = sorted(int(r["nw"]) for r in g)
        f = lambda m, se, w: f"{m:{w}.0f} +/- {se:.0f}" if se is not None else f"{m:{w}.0f}"
        print(f"  {name:14s} {n:2d}  {f(nw, nse, 7):>16s}  {f(lh, lse, 4):>12s}  {cl:12.2f}  {(wl or 0):7.2f}  "
              f"{nws[0]:,}-{nws[-1]:,}")
        if base is None:
            base = (name, nw, nse)
        elif nse is not None and base[2] is not None:
            d, se = nw - base[1], math.sqrt(nse ** 2 + base[2] ** 2)
            verdict = "real" if abs(d) > 2 * se else "could be luck"
            print(f"  {'':14s}     vs {base[0]}: {d:+.0f} net worth ({verdict}: +/-{2 * se:.0f} at ~95%)")
    print("  (+/- is the standard error of the average; a difference needs to be about twice its +/- to trust it)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--only", choices=list(SETUPS), action="append")
    ap.add_argument("--report", nargs="?", const="latest")
    a = ap.parse_args()
    if a.report:
        path = max(glob.glob(os.path.join(RUNS, "batch_*.csv")), key=os.path.getmtime) if a.report == "latest" else a.report
        return report(path)
    setups = a.only or list(SETUPS)
    os.makedirs(RUNS, exist_ok=True)
    path = os.path.join(RUNS, time.strftime("batch_%Y-%m-%d_%H%M.csv"))
    with open(path, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=FIELDS).writeheader()
    order = [s for _ in range(a.runs) for s in setups]          # round-robin: slow drift hits every setup alike
    print(f"{len(order)} runs ({', '.join(setups)} x {a.runs}) -> {path}")
    t0 = time.time()
    status = {"csv": os.path.basename(path), "order": order, "start": t0}

    def save_status(**kw):                                       # for lab_hud.py --batch
        status.update(kw)
        try:
            with open(os.path.join(RUNS, "batch_status.json"), "w", encoding="utf-8") as f:
                json.dump(status, f)
        except OSError:
            pass
    try:
        for i, setup in enumerate(order, 1):
            save_status(i=i, setup=setup, game_start=time.time())
            print(f"[{i}/{len(order)}] {setup} ...", flush=True)
            r = one_run(setup)
            with open(path, "a", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore").writerow(r)
            left = (time.time() - t0) / i * (len(order) - i)
            print(f"   {r['status']}: nw {r.get('nw')}, lh {r.get('lh')}, camp {r.get('camp_lh')}/trip "
                  f"| ~{left / 60:.0f} min left", flush=True)
        save_status(i=len(order) + 1, setup=None, done=True)
    except KeyboardInterrupt:
        print("stopped")
        save_status(stopped=True)
        close_dota()
    report(path)


if __name__ == "__main__":
    main()
