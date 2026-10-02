"""The March footprint lab (bot.py --lab 1 --lab-footprint 2): where one March does damage, shielding, camp angles.

    python fp_report.py                  the latest footprint run
    python fp_report.py <run.jsonl>

One March is cast due east from Tinker (cast point 250 ahead); creeps are rooted and disarmed.
  grid    robot hits on a lone high-HP dummy at each spot (along = in the March direction, side = sideways)
  shield  hits on a dummy with another dummy 150/300 in front of it, against the same spot alone
  angle   a real camp 600/900 from Tinker, the March cast 0-180 deg off it: kills and HP taken
"""
from __future__ import annotations

import collections
import glob
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def latest():
    runs = [p for p in glob.glob(os.path.join(HERE, "bot_runs", "*.jsonl"))
            if '"footprint": true' in open(p, encoding="utf-8", errors="replace").read(30000)]
    return max(runs, key=os.path.getmtime) if runs else None


def lost(c):
    end = 0 if c.get("died") is not None else (c["tl"][-1][1] if c["tl"] else c["hp0"])
    return c["hp0"] - end


def first_hit(c):
    return next((t for t, hp in c["tl"] if hp < c["hp0"]), None)


def hit_size(rows, lvl):
    """One robot's damage on the dummy: the most common single HP drop between two samples."""
    drops = collections.Counter()
    for r in rows:
        if r["test"] != "grid" or r["march"] != lvl:
            continue
        tl = r["creeps"][0]["tl"]
        for (_, a), (_, b) in zip(tl, tl[1:]):
            if 0 < a - b < 200:
                drops[a - b] += 1
    return drops.most_common(1)[0][0] if drops else None


def main(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if '"lab_fp"' in l]
    print(f"{os.path.basename(path)}: {len(rows)} footprint tests (one March each, cast due east)\n")
    for lvl in sorted({r["march"] for r in rows}):
        hs = hit_size(rows, lvl)
        grid = collections.defaultdict(list)
        first = collections.defaultdict(list)
        for r in rows:
            if r["test"] == "grid" and r["march"] == lvl:
                c = r["creeps"][0]
                grid[(c["al"], c["sd"])].append(lost(c) / hs)
                if first_hit(c) is not None:
                    first[c["al"]].append(first_hit(c))
        als = sorted({k[0] for k in grid}, reverse=True)
        sds = sorted({k[1] for k in grid})
        print(f"March {lvl}: robot hits on a lone dummy (1 hit = {hs} HP), Tinker at along 0 / side 0, robots go up")
        print("  along\\side " + "".join(f"{s:>6d}" for s in sds) + "   first hit (median s)")
        for al in als:
            cells = "".join(f"{statistics.mean(grid[(al, s)]):6.1f}" if grid.get((al, s)) else "     ." for s in sds)
            f = first.get(al)
            print(f"  {al:>9d} {cells}   {statistics.median(f):.1f}" if f else f"  {al:>9d} {cells}")
        print()
    sh = collections.defaultdict(list)
    for r in rows:
        if r["test"] != "shield":
            continue
        by = {c["role"]: c for c in r["creeps"]}
        sh[(r["march"], r["front"], r["gap"], r["side"])].append((lost(by["front"]), lost(by["back"])))
    if sh:
        print("shielding: HP lost by the front dummy and the one behind it (robots come from below)")
        print("  March  front  gap  side   front lost   back lost")
        for k in sorted(sh):
            v = sh[k]
            print(f"  {k[0]:>5d} {k[1]:>6d} {k[2]:>4d} {k[3]:>5d}   {statistics.mean(x for x, _ in v):10.0f}   "
                  f"{statistics.mean(y for _, y in v):9.0f}")
        print()
    an = collections.defaultdict(list)
    for r in rows:
        if r["test"] != "angle":
            continue
        cs = r["creeps"]
        kills = sum(1 for c in cs if c.get("died") is not None)
        hp = sum(lost(c) for c in cs) / sum(c["max"] for c in cs)
        an[(r["march"], r["dist"], r["off"])].append((kills, len(cs), hp))
    if an:
        print("camp angle: one March, a camp at `dist` from Tinker, `off` = degrees between the March and the camp")
        print("  (0 = cast straight at it, 90 = the camp off to the side, 180 = the camp behind Tinker)")
        print("  March  dist   off   kills   camp HP taken")
        for k in sorted(an):
            v = an[k]
            print(f"  {k[0]:>5d} {k[1]:>5d} {k[2]:>5d}   {statistics.mean(x for x, _, _ in v):.1f}/{v[0][1]}   "
                  f"{statistics.mean(z for _, _, z in v):6.0%}")


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else latest()
    if not p:
        sys.exit("no footprint run in bot_runs/")
    main(p)
