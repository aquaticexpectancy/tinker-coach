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
SETUPS["lab_10x"] = SETUPS["lab"] + ["--speed", "10"]    # speed check: the same bot at 10x instead of 2x
SETUPS["brute4_10x"] = SETUPS["lab_10x"] + ["--min-marches", "4"]   # at least 4 Marches a camp trip (mana allowing)
SETUPS["aim_10x"] = SETUPS["lab_10x"] + ["--aim", "on"]    # Marches aimed at the creeps at C, D, E (A keeps the facing)
SETUPS["stack_10x"] = SETUPS["lab_10x"] + ["--ancient-stack"]   # your 7:46 ancient stack, then farm it
SETUPS["awake_10x"] = SETUPS["lab_10x"] + ["--laser-awake"]   # camp Lasers only at awake creeps (night)
SETUPS["a3_10x"] = SETUPS["lab_10x"] + ["--a-marches", "3"]   # 3 Marches at A with March 4 (lab: 2 + Laser)
SETUPS["pull_10x"] = SETUPS["lab_10x"] + ["--stand-pull", "350"]   # stand 350 closer to A's camps
SETUPS["boxes_10x"] = SETUPS["lab_10x"] + ["--real-camps"]   # camps from the map's spawn boxes (A, E: 2 each)
SETUPS["af300_10x"] = SETUPS["lab_10x"] + ["--a-face", "300"]   # A lab 10-02: facing 300 beat 325 by ~10 points
SETUPS["af0_10x"] = SETUPS["lab_10x"] + ["--a-face", "0"]       # ... and so did 0
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


KEEP = False                                # --keep-dota: one Dota for the whole batch, games load in it


def quit_dota():
    """--keep-dota: close Dota through its own console (a normal quit), else the usual close."""
    import socket
    try:
        with socket.create_connection(("127.0.0.1", 2121), timeout=3) as c:   # bot.py NETCON
            c.sendall(b"quit\n")
        for _ in range(30):
            if "dota2.exe" not in subprocess.run(["tasklist", "/FI", "IMAGENAME eq dota2.exe"],
                                                 capture_output=True, text=True).stdout.lower():
                return
            time.sleep(1)
    except OSError:
        pass
    close_dota()


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
    if not KEEP:
        close_dota()
    cmd = [sys.executable, "-u", os.path.join(HERE, "bot.py"), *COMMON, *SETUPS[setup]]   # a setup's own --speed wins
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
    if not KEEP or status == "timeout":       # a stuck game: start the next one in a fresh Dota
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
    ap.add_argument("--keep-dota", action="store_true",
                    help="launch Dota once and load every game in it (~30 s a load instead of ~90 s); quit at the end")
    a = ap.parse_args()
    global KEEP
    KEEP = a.keep_dota
    if KEEP:
        COMMON.append("--keep-dota")
        close_dota()                                              # a Dota without the console port can't be reused
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
        if KEEP:
            quit_dota()
    except KeyboardInterrupt:
        print("stopped")
        save_status(stopped=True)
        quit_dota() if KEEP else close_dota()
    report(path)


if __name__ == "__main__":
    main()
