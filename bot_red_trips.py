"""Why trips come back red (0-1 last hits): sorts every such trip in the bot runs by cause.

    python bot_red_trips.py              all batch runs (bot_runs/batch_*.csv)
    python bot_red_trips.py <run.jsonl>  one run, with every red trip listed

Causes, checked in this order:
  wave_empty     a mid-wave trip that killed 0-1
  ghost          no living creeps at the station when Tinker landed
  leftovers      same station earlier in this minute, or since its last :00 the camp was left with creeps (they
                 block the spawn): the trip went back for creeps an earlier trip couldn't kill
  missed         creeps there, but the station's creep HP barely dropped during the trip (< 15%): the Marches
                 didn't reach them
  tanky          the HP dropped but they survived (ancients, big creeps)
"""
from __future__ import annotations

import collections
import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "bot_runs")


def load(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return rows


def classify(rows):
    """Yield (trip record, cause, detail) for each red trip."""
    landed, prev_trip = None, {}
    seen_on_land = collections.defaultdict(list)
    hp_marks = []                    # (clock, station, hp left) from the March skip / plan-end logs
    for r in rows:
        k = r.get("kind")
        if k == "landed":
            landed = r
            seen_on_land[r["station"]] = []
        elif k == "camp_seen" and landed and r["station"] == landed["station"] and r["clock"] - landed["clock"] < 4:
            seen_on_land[r["station"]].append(r["actual"])
        elif k == "skip" and "HP left" in r.get("why", ""):
            hp_marks.append((r["clock"], landed and landed["station"], int(r["why"].split()[0])))
        elif k == "trip":
            st = r["station"]
            start = r["clock"] - r.get("seconds", 0)
            last = prev_trip.get(st)
            prev_trip[st] = r
            if r["last_hits"] > 1:
                continue
            if st == "B":
                yield r, "wave_empty", ""
                continue
            seen = seen_on_land.get(st) or []
            if seen and sum(seen) == 0:
                yield r, "ghost", "0 creeps on landing"
                continue
            if last and last.get("creeps_left", 0) > 0:
                same_min = int(last["clock"] // 60) == int(start // 60)
                yield r, "leftovers", f"previous trip at {fmt(last['clock'])} left {last['creeps_left']}" + \
                    (" (same minute)" if same_min else " (they block the spawn)")
                continue
            marks = [h for c, s, h in hp_marks if s == st and start - 2 <= c <= r["clock"]]
            if len(marks) >= 1 and r.get("creeps_left", 0) > 0:
                yield r, "tanky", f"{marks[-1]:,} HP still standing"
            else:
                yield r, "missed", f"{r.get('creeps_left', 0)} creeps left untouched"


def fmt(c):
    c = int(c)
    return f"{c // 60}:{c % 60:02d}"


def main():
    if len(sys.argv) > 1:
        paths = sys.argv[1:]
    else:
        paths = []
        for b in sorted(glob.glob(os.path.join(RUNS, "batch_*.csv"))):
            paths += [os.path.join(RUNS, r["run"]) for r in csv.DictReader(open(b, encoding="utf-8"))
                      if r["status"] == "ok" and r["run"]]
    causes, camp_trips, red_secs = collections.Counter(), 0, collections.Counter()
    by_station = collections.Counter()
    for path in paths:
        rows = load(path)
        camp_trips += sum(1 for r in rows if r.get("kind") == "trip" and r["station"] != "B")
        for r, cause, detail in classify(rows):
            causes[cause] += 1
            red_secs[cause] += r.get("seconds", 0) + 10          # + the Keen there and the fountain stop after
            by_station[(cause, r["station"])] += 1
            if len(paths) == 1:
                print(f"  {fmt(r['clock'])}  {r['station']} +{r['last_hits']}  {cause:10s} {detail}")
    n = sum(causes.values())
    print(f"{len(paths)} runs, {camp_trips} camp trips, {n} red trips (0-1 last hits)")
    for cause, c in causes.most_common():
        st = ", ".join(f"{s} {by_station[(cause, s)]}" for s in "ABCDE" if by_station[(cause, s)])
        print(f"  {cause:10s} {c:3d}  ~{red_secs[cause] / len(paths):4.0f} s a game   ({st})")


if __name__ == "__main__":
    main()
