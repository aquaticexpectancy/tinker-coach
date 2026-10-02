"""Your F11 drill run as trips, next to the bot's: where you went, when, how long, what each visit earned.

    python drill_trips.py                          your best drill (bot.DRILL_DEFAULT) vs the latest batch
    python drill_trips.py <session.jsonl> [batch.csv]

Your session is the game-state feed (~1 sample a second); a trip = consecutive samples nearest the same station
(the bot's stand spots, the mid wave and the fountain), last hits counted until 3 s after you leave (robots still out).
"""
from __future__ import annotations

import collections
import csv
import glob
import json
import math
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bot  # noqa: E402

SPOTS = {st: s["stand"] for st, s in bot.STATIONS.items() if s.get("stand")}
SPOTS["B"] = (-964, -871)                  # the mid-lane spot the bot lands on for the wave
SPOTS["F"] = (-6950, -6450)                # Radiant fountain
NEAR = 1600


def where(x, y):
    st, d = min(((k, math.hypot(x - a, y - b)) for k, (a, b) in SPOTS.items()), key=lambda z: z[1])
    return st if d < NEAR else "-"


def your_trips(path, t0=300, t1=600):
    rows = []
    for l in open(path, encoding="utf-8"):
        p = json.loads(l).get("p", {})
        m, h, pl = p.get("map", {}), p.get("hero", {}), p.get("player", {})
        if "clock_time" in m and "xpos" in h:
            ab = p.get("abilities", {})
            mcd = next((a.get("cooldown", 0) for a in ab.values() if a.get("name") == "tinker_march_of_the_machines"), 0)
            rows.append((m["clock_time"], where(h["xpos"], h["ypos"]), pl.get("last_hits", 0), h.get("mana", 0), mcd))
    rows = [r for r in rows if t0 - 2 <= r[0] <= t1]
    trips, cur = [], None
    for i, (c, st, lh, mana, mcd) in enumerate(rows):
        if cur is None or st != cur["st"]:
            if cur:
                trips.append(cur)
            cur = {"st": st, "start": c, "end": c, "i0": i, "marches": 0, "mana0": mana}
        cur["end"] = c
        if i and mcd > rows[i - 1][4] + 1:                  # the cooldown jumped: a March (or a Rearm reset it)
            cur["marches"] += 1
    if cur:
        trips.append(cur)
    out = []
    for tr in trips:
        lh0 = rows[tr["i0"]][2]
        after = [r[2] for r in rows if r[0] <= tr["end"] + 3]
        tr["lh"] = (after[-1] if after else lh0) - lh0
        tr["secs"] = tr["end"] - tr["start"] + 1
        out.append(tr)
    return [t for t in out if t["st"] != "-" or t["secs"] >= 3]


def bot_trips(batch):
    runs = [r["run"] for r in csv.DictReader(open(batch, encoding="utf-8")) if r.get("run")]
    per = []
    for run in runs:
        trips = [json.loads(l) for l in open(os.path.join(HERE, "bot_runs", run), encoding="utf-8") if '"kind": "trip"' in l]
        per.append(trips)
    return per


def main(args):
    sess = args[0] if args else os.path.join(HERE, "sessions", bot.DRILL_DEFAULT + ".jsonl")
    batch = args[1] if len(args) > 1 else max(glob.glob(os.path.join(HERE, "bot_runs", "batch_*.csv")), key=os.path.getmtime)
    yt = your_trips(sess)
    print(f"YOU ({os.path.basename(sess)}), 5:00-10:00:")
    print("  start  where  secs  marches  LH")
    for t in yt:
        if t["st"] in "-":
            continue
        print(f"  {int(t['start']) // 60}:{int(t['start']) % 60:02d}   {t['st']:>3s}  {t['secs']:5.0f}  {t['marches']:7d}  {t['lh']:3d}")
    camp = [t for t in yt if t["st"] in "ACDE"]
    print(f"\n  per station (you):")
    for st in "ABCDEF":
        v = [t for t in yt if t["st"] == st]
        if v:
            print(f"    {st}: {len(v)} visits, {sum(t['secs'] for t in v):.0f} s there, {sum(t['lh'] for t in v)} LH, "
                  f"{sum(t['lh'] for t in v) / len(v):.1f} LH a visit")
    per = bot_trips(batch)
    print(f"\nBOT ({os.path.basename(batch)}, {len(per)} games), per game on average:")
    for st in "ABCDE":
        v = [[t for t in g if t["station"] == st] for g in per]
        n = statistics.mean(len(x) for x in v)
        lh = statistics.mean(sum(t["last_hits"] for t in x) for x in v)
        s = statistics.mean(sum(t.get("seconds", 0) for t in x) for x in v)
        print(f"    {st}: {n:.1f} visits, {s:.0f} s there, {lh:.1f} LH, {lh / n if n else 0:.1f} LH a visit")
    print(f"\n  camp visits: you {len(camp)}, bot {statistics.mean(len([t for t in g if t['station'] != 'B']) for g in per):.1f}")


if __name__ == "__main__":
    main(sys.argv[1:])
