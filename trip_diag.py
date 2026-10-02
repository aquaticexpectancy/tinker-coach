"""Why camp trips leave creeps alive: reads the trip traces (trip_creeps, every 0.5 s) of bot runs.

    python trip_diag.py bot_runs/batch_2026-10-01_2120.csv     every game of a batch
    python trip_diag.py bot_runs/2026-10-01_2120.jsonl ...     those games

For every creep alive when Tinker left a camp, one cause, checked in this order:
  never_in_path  never inside a March's path (the bot's own model: -100..1500 ahead, 450 either side) while
                 the robots of that March were walking (6 s after the cast)
  walked_off     was in a path, but moved 400+ units during the trip (pulled toward Tinker, or chasing)
  tanky          was in a path and lost 35%+ of its HP, but survived
  barely_hit     was in a path and lost under 35%: the robots were there but didn't hit it much
Trip lines also count families at landing: more creeps than the station's camps hold = leftovers stacked up.
"""
from __future__ import annotations

import collections
import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "bot_runs")
ROBOT_S = 6.0                       # a March's robots walk ~6 s
CAMPS = {"A": 2, "C": 2, "D": 2, "E": 1}   # camps a station's March covers (C: hard + ancients)
FULL = {"A": 7, "C": 8, "D": 7, "E": 4}    # rough creep count when every camp is full (more = stacked leftovers)


def in_path(cx, cy, m):
    a = math.radians(m["yaw"])
    dx, dy = math.cos(a), math.sin(a)
    vx, vy = cx - m["x"], cy - m["y"]
    along = vx * dx + vy * dy
    return -100 < along < 1500 and abs(vx * dy - vy * dx) < 450


def trips_of(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    out = collections.OrderedDict()
    marches = [r for r in rows if r.get("kind") == "cast" and r.get("ability") == "march" and "yaw" in r]
    for r in rows:
        if r.get("kind") != "trip_creeps":
            continue
        key = (r["station"], r["start"])
        tr = out.setdefault(key, {"station": r["station"], "start": r["start"], "samples": []})
        tr["samples"].append(r)
    for tr in out.values():
        c0, c1 = tr["samples"][0]["clock"], tr["samples"][-1]["clock"]
        tr["marches"] = [m for m in marches if c0 - 0.5 <= m["clock"] <= c1 + 0.5]
    return list(out.values())


def diagnose(tr):
    s = tr["samples"]
    seen = {}                                   # id -> list of (clock, name, hp, max, x, y)
    for r in s:
        for c in r["creeps"] or []:
            seen.setdefault(c[0], []).append((r["clock"], *c[1:]))
    # the trip's creeps: within the bot's target range (1300, Targets()) of Tinker when the first March went out;
    # the trace reaches 1800, which also takes in neighbouring camps the trip never aimed at
    m0 = tr["marches"][0]["clock"]
    at = min(s, key=lambda r: abs(r["clock"] - m0))
    first = [c for c in (at["creeps"] or []) if math.hypot(c[4] - at["hx"], c[5] - at["hy"]) <= 1300]
    mine = {c[0] for c in first}
    last_ids = {c[0] for c in (s[-1]["creeps"] or [])} & mine
    out = []
    for cid in last_ids:
        hist = seen[cid]
        name, hp0, mx = hist[0][1], hist[0][2], hist[0][3]
        hp1 = hist[-1][2]
        hit = any(in_path(x, y, m) for (cl, _, _, _, x, y) in hist for m in tr["marches"]
                  if m["clock"] <= cl <= m["clock"] + ROBOT_S)
        moved = math.hypot(hist[-1][4] - hist[0][4], hist[-1][5] - hist[0][5])
        lost = (hp0 - hp1) / mx if mx else 0
        if not hit:
            cause = "never_in_path"
        elif moved >= 400:
            cause = "walked_off"
        elif lost >= 0.35:
            cause = "tanky"
        else:
            cause = "barely_hit"
        out.append({"name": name, "cause": cause, "hp": hp1, "max": mx, "lost": lost, "moved": moved,
                    "dist": math.hypot(hist[-1][4] - s[-1]["hx"], hist[-1][5] - s[-1]["hy"])})
    return {"landing": len(first), "left": out, "marches": len(tr["marches"]),
            "stacked": len(first) > FULL.get(tr["station"], 99)}


def main(args):
    paths = []
    for a in args or []:
        if a.endswith(".csv"):
            paths += [os.path.join(RUNS, r["run"]) for r in csv.DictReader(open(a, encoding="utf-8")) if r.get("run")]
        else:
            paths.append(a)
    if not paths:
        sys.exit(__doc__)
    by_cause = collections.Counter()
    by_station = collections.defaultdict(collections.Counter)
    trips = left_trips = stacked = 0
    st_trips = collections.Counter()
    st_land = collections.defaultdict(list)
    names = collections.defaultdict(collections.Counter)
    for p in paths:
        for tr in trips_of(p):
            if not tr["marches"]:
                continue
            d = diagnose(tr)
            trips += 1
            st = tr["station"]
            st_trips[st] += 1
            st_land[st].append(d["landing"])
            stacked += d["stacked"]
            if d["left"]:
                left_trips += 1
            for c in d["left"]:
                by_cause[c["cause"]] += 1
                by_station[st][c["cause"]] += 1
                names[c["cause"]][c["name"]] += 1
    total = sum(by_cause.values())
    print(f"{len(paths)} games, {trips} camp trips with Marches, {left_trips} left creeps alive, "
          f"{total} creeps left in all; {stacked} trips landed on more creeps than full camps hold")
    print("\ncreeps left, by cause")
    for cause, n in by_cause.most_common():
        top = ", ".join(f"{k} {v}" for k, v in names[cause].most_common(4))
        print(f"  {cause:14s} {n:4d}  {n / total:4.0%}   ({top})")
    print("\nby station: trips, creeps at landing (avg), left per trip, causes")
    for st in sorted(st_trips):
        n = sum(by_station[st].values())
        land = sum(st_land[st]) / len(st_land[st])
        causes = ", ".join(f"{k} {v}" for k, v in by_station[st].most_common())
        print(f"  {st}  {st_trips[st]:3d} trips  {land:4.1f} at landing  {n / st_trips[st]:4.1f} left   {causes}")


if __name__ == "__main__":
    main(sys.argv[1:])
