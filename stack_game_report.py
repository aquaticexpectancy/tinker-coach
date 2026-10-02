"""A batch's games side by side: last hits / net worth by minute, every trip, and the ancient stack.

    python stack_game_report.py bot_runs/batch_2026-10-02_0118.csv

Per game: LH at 6:00..10:00, the stack (stacked? hit landed, HP after), then each trip as
"clock station LH (marches)". Per setup: the average LH gained in each minute, to see where a setup wins/loses.
"""
from __future__ import annotations

import collections
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    return [json.loads(l) for l in open(os.path.join(HERE, "bot_runs", name), encoding="utf-8")]


def at(rows, t, key):
    best = None
    for r in rows:
        if r.get("kind") == "snap" and r["clock"] <= t:
            best = r.get(key)
    return best


def main(path):
    games = collections.defaultdict(list)
    for row in csv.DictReader(open(path, encoding="utf-8")):
        if row["status"] == "ok":
            games[row["setup"]].append(row["run"])
    mins = [300, 360, 420, 480, 540, 600]
    for setup, runs in games.items():
        gain = collections.defaultdict(list)
        print(f"== {setup}")
        for run in runs:
            rows = load(run)
            lh = [at(rows, t, "lh") or 0 for t in mins]
            for a, b, t in zip(lh, lh[1:], mins[1:]):
                gain[t].append(b - a)
            st = [r for r in rows if r.get("kind") == "stack" and r.get("step") in ("leave", "no target", "no stack (no ancients / no mana)")]
            sline = " ".join(f"[{r['step']} {r.get('why', '')} stacked={r.get('stacked')} hit={r.get('hit1')} hp={r.get('hp')}]" for r in st)
            trips = " ".join(f"{int(r['clock'] // 60)}:{int(r['clock'] % 60):02d}{r['station']}{r['last_hits']}({r['marches']})"
                             for r in rows if r.get("kind") == "trip")
            print(f"  {run}  LH by min {lh}  nw {at(rows, 600, 'nw')}  {sline}")
            print(f"     trips: {trips}")
        print("  LH gained per minute (avg): " + "  ".join(f"{t // 60 - 1}-{t // 60}: {sum(v) / len(v):.1f}" for t, v in sorted(gain.items())))


if __name__ == "__main__":
    main(sys.argv[1])
