"""Your stacking drill attempts (bot.py --stack-drill): what the successful pulls had in common.

    python stack_report.py                       every drill since 10-02
    python stack_report.py <run.jsonl> ...

Per attempt, from the 0.2 s samples (not from button presses):
  hit       the first creep whose HP dropped after :47 = your hit landed (and its spawn box)
  2nd hit   the first creep of the OTHER box that lost HP (you tagging a second camp)
  moving    when the hit camp started leaving its box (a creep 150+ from its :47 spot)
  out       when every creep that stood in the hit box at :47 was outside it
  walk      how far you were from the hit box at the hit and at :00 (edge distance), and how far you walked
  result    the game's own stack marker per box
"""
from __future__ import annotations

import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def edge_dist(b, x, y):
    dx = max(b["min"][0] - x, 0, x - b["max"][0])
    dy = max(b["min"][1] - y, 0, y - b["max"][1])
    return math.hypot(dx, dy)


def inside(b, x, y, m=0):
    return b["min"][0] - m <= x <= b["max"][0] + m and b["min"][1] - m <= y <= b["max"][1] + m


def attempts(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    boxes = {}
    for r in rows:
        if r.get("kind") == "stack_drill":
            boxes = {b["name"]: b for b in r["boxes"]}
        if r.get("kind") == "stack_attempt" and r.get("samples") and boxes:
            yield r, boxes


def fmt(t):
    return f"{int(t) // 60}:{t % 60:04.1f}" if t is not None else "  -   "


def analyse(r, boxes):
    s = [x for x in r["samples"] if x[0] % 60 >= 46.9 or x[0] % 60 < 2]
    first = {c[0]: c for c in s[0][4]}
    home = {}                                              # creep id -> its box at :47
    for cid, c in first.items():
        for n, b in boxes.items():
            if inside(b, c[3], c[4], 150):
                home[cid] = n
    hit = second = None
    for smp in s:
        for c in smp[4]:
            f = first.get(c[0])
            if not f or c[2] >= f[2]:
                continue
            if hit is None:
                hit = {"t": smp[0], "name": c[1], "box": home.get(c[0]), "hero": (smp[1], smp[2])}
            elif second is None and home.get(c[0]) and home.get(c[0]) != hit["box"]:
                second = {"t": smp[0], "name": c[1], "box": home.get(c[0])}
    if not hit or not hit["box"]:
        return None
    b = boxes[hit["box"]]
    camp = [cid for cid, n in home.items() if n == hit["box"]]
    moving = out = None
    for smp in s:
        if smp[0] < hit["t"]:
            continue
        pos = {c[0]: c for c in smp[4]}
        if moving is None and any(cid in pos and math.hypot(pos[cid][3] - first[cid][3], pos[cid][4] - first[cid][4]) > 150 for cid in camp):
            moving = smp[0]
        if out is None and camp and all(cid in pos and not inside(b, pos[cid][3], pos[cid][4]) for cid in camp):
            out = smp[0]
    end = min(s, key=lambda x: abs(x[0] % 60 - 0) if x[0] % 60 < 2 else 99)
    h0, h1 = hit["hero"], (end[1], end[2])
    res = {x["box"]: x for x in r["result"]}
    return {"minute": r["minute"], "hit": hit, "second": second, "moving": moving, "out": out,
            "edge_at_hit": edge_dist(b, *h0), "edge_at_00": edge_dist(b, *h1), "walked": math.hypot(h1[0] - h0[0], h1[1] - h0[1]),
            "stacked": res.get(hit["box"], {}).get("stacked"), "other": {n: v.get("stacked") for n, v in res.items() if n != hit["box"]},
            "camp_size": len(camp)}


def main(paths):
    if not paths:
        paths = sorted(p for p in glob.glob(os.path.join(HERE, "bot_runs", "2026-10-02_*.jsonl"))
                       if '"stack_drill"' in open(p, encoding="utf-8", errors="replace").read(80000))
    out = []
    for p in paths:
        for r, boxes in attempts(p):
            a = analyse(r, boxes)
            if a:
                out.append(a)
    print(f"{len(out)} attempts with a hit ({', '.join(os.path.basename(p) for p in paths)})\n")
    print("  minute  hit landed  on                 box     2nd hit      moving   all out  edge@hit edge@:00 walked  stacked")
    for a in out:
        h, s2 = a["hit"], a["second"]
        print(f"  {a['minute']:>5d}   {fmt(h['t'])}  {h['name'][:18]:18s} {h['box'][-6:]}  "
              f"{fmt(s2['t']) if s2 else '   -  '}  {fmt(a['moving'])}  {fmt(a['out'])}  "
              f"{a['edge_at_hit']:7.0f} {a['edge_at_00']:8.0f} {a['walked']:6.0f}   {'YES' if a['stacked'] else 'no'}")
    ok = [a for a in out if a["stacked"]]
    if ok:
        sec = lambda t: t % 60
        print(f"\n  stacked {len(ok)}/{len(out)}")
        print(f"  hit landed      :{min(sec(a['hit']['t']) for a in ok):.1f} - :{max(sec(a['hit']['t']) for a in ok):.1f}"
              f"  (avg :{sum(sec(a['hit']['t']) for a in ok) / len(ok):.1f})")
        mv = [sec(a['moving']) - sec(a['hit']['t']) for a in ok if a['moving']]
        if mv:
            print(f"  camp moving     {min(mv):.1f} - {max(mv):.1f} s after the hit")
        ot = [sec(a['out']) for a in ok if a['out']]
        if ot:
            print(f"  camp all out    :{min(ot):.1f} - :{max(ot):.1f}")
        print(f"  you from box    {min(a['edge_at_hit'] for a in ok):.0f}-{max(a['edge_at_hit'] for a in ok):.0f} at the hit, "
              f"{min(a['edge_at_00'] for a in ok):.0f}-{max(a['edge_at_00'] for a in ok):.0f} at :00; walked "
              f"{min(a['walked'] for a in ok):.0f}-{max(a['walked'] for a in ok):.0f}")


if __name__ == "__main__":
    main(sys.argv[1:])
