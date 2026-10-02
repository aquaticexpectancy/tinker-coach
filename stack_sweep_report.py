"""The bot's stacking sweep (bot.py --stack-drill C --stack-bot N) next to your stacks: what makes a stack.

    python stack_sweep_report.py <sweep.jsonl> [your drill .jsonl ...]

Per test: did the camp that was hit FIRST stack (the game's marker), when the hit landed, how far Tinker was from
that camp's box at the hit, how many of the camp's creeps were out of their box at :00, and where Tinker was.
Grouped by test kind (timing / retreat / second hit), then the stacked vs failed tests compared, then your pulls.
"""
from __future__ import annotations

import collections
import json
import math
import sys


def inside(b, x, y, m=0):
    return b["min"][0] - m <= x <= b["max"][0] + m and b["min"][1] - m <= y <= b["max"][1] + m


def edge(b, x, y):
    return math.hypot(max(b["min"][0] - x, 0, x - b["max"][0]), max(b["min"][1] - y, 0, y - b["max"][1]))


def runs(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    boxes = None
    for r in rows:
        if r.get("kind") == "stack_drill":
            boxes = {b["name"]: b for b in r["boxes"]}
        elif r.get("kind") == "stack_attempt" and boxes and r.get("samples"):
            yield r, boxes


def measure(r, boxes, box1=None, hit_t=None):
    s = r["samples"]
    first = s[0]
    home = {}
    for c in first[4]:
        for n, b in boxes.items():
            if inside(b, c[3], c[4], 150):
                home[c[0]] = n
    if box1 is None or hit_t is None:                      # your attempts: the first creep that lost HP
        f0 = {c[0]: c for c in first[4]}
        for smp in s:
            hit = next((c for c in smp[4] if c[0] in f0 and c[2] < f0[c[0]][2]), None)
            if hit:
                box1, hit_t = home.get(hit[0]), smp[0]
                break
    if not box1 or hit_t is None:
        return None
    b = boxes[box1]
    camp = [cid for cid, n in home.items() if n == box1]
    at_hit = min(s, key=lambda x: abs(x[0] - hit_t))
    at00 = next((x for x in s if x[0] % 60 < 0.5), s[-1])
    pos00 = {c[0]: c for c in at00[4]}
    out = sum(1 for cid in camp if cid in pos00 and not inside(b, pos00[cid][3], pos00[cid][4]))
    res = {x["box"]: x for x in r["result"]}
    return {"box1": box1, "hit": hit_t % 60, "dist_at_hit": edge(b, at_hit[1], at_hit[2]),
            "camp": len(camp), "out_at_00": out, "hero_edge_00": edge(b, at00[1], at00[2]),
            "hero_in_box_00": inside(b, at00[1], at00[2]), "stacked": bool(res.get(box1, {}).get("stacked"))}


def main(args):
    sweep, mine = args[0], args[1:]
    tests = []
    for r, boxes in runs(sweep):
        T = r.get("bot_test")
        if not T or not T.get("hit1"):
            continue
        m = measure(r, boxes, T["box1"], r["minute"] * 60 + T["hit1"])
        if m:
            tests.append({**T, **m})
    print(f"{len(tests)} bot tests with a hit\n")
    for kind, keys in (("timing", ("land",)), ("retreat", ("walk", "dir")), ("second", ("second",))):
        g = collections.defaultdict(list)
        for t in tests:
            if t["kind"] == kind:
                g[tuple(t.get(k, 0) for k in keys)].append(t)
        print(f"{kind}: stacked / tests  (camp creeps out of the box at :00, avg)")
        for k in sorted(g):
            v = g[k]
            print(f"  {' '.join(f'{a}={b}' for a, b in zip(keys, k)):18s} {sum(t['stacked'] for t in v)}/{len(v)}"
                  f"   out {sum(t['out_at_00'] for t in v) / len(v):.1f} of {sum(t['camp'] for t in v) / len(v):.1f}")
        print()
    for label, grp in (("bot stacked", [t for t in tests if t["stacked"]]), ("bot failed", [t for t in tests if not t["stacked"]])):
        if grp:
            avg = lambda k: sum(t[k] for t in grp) / len(grp)
            print(f"{label:12s} n={len(grp):2d}  hit :{avg('hit'):.1f}  from box {avg('dist_at_hit'):4.0f}  "
                  f"creeps out at :00 {avg('out_at_00'):.1f}/{avg('camp'):.1f}  Tinker from box at :00 {avg('hero_edge_00'):4.0f}")
    you = []
    for p in mine:
        for r, boxes in runs(p):
            m = measure(r, boxes)
            if m:
                you.append(m)
    if you:
        avg = lambda k: sum(t[k] for t in you) / len(you)
        print(f"{'you':12s} n={len(you):2d}  hit :{avg('hit'):.1f}  from box {avg('dist_at_hit'):4.0f}  "
              f"creeps out at :00 {avg('out_at_00'):.1f}/{avg('camp'):.1f}  Tinker from box at :00 {avg('hero_edge_00'):4.0f}"
              f"  stacked {sum(t['stacked'] for t in you)}/{len(you)}")


if __name__ == "__main__":
    main(sys.argv[1:])
