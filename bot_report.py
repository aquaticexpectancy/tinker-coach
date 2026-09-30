"""Summarise a bot run: net worth per minute against your F11 run, trips, fountain stops, decisions, errors.

    python bot_report.py                 latest run in bot_runs/
    python bot_report.py <run.jsonl>
"""
import collections
import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main(path=None):
    path = path or max(glob.glob(os.path.join(HERE, "bot_runs", "*.jsonl")), key=os.path.getmtime)
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    snaps = [r for r in rows if r["kind"] == "snap"]
    start = next((r for r in rows if r["kind"] == "drill_start"), None)
    mine = {}
    if start:
        sess = start.get("state", "")[:15]
        for r in csv.DictReader(open(os.path.join(HERE, "runs.csv"), encoding="utf-8")):
            if r["session"] == sess and r.get("net_worth"):
                mine[int(r["minute"])] = (int(r["net_worth"]), int(r["lh"] or 0))
    at = lambda c: next((s for s in snaps if s["clock"] >= c), snaps[-1] if snaps else None)
    print(os.path.basename(path), "| drill start:", start and start.get("state"))
    print("  min   bot nw   you nw   diff | bot lh  you lh")
    for m in range(5, 11):
        s = at(m * 60)
        if not s or s["clock"] < m * 60 - 2:
            break
        y = mine.get(m, (None, None))
        diff = f"{s['nw'] - y[0]:+6d}" if y[0] else "     -"
        print(f"  {m:2d}:00  {s['nw']:6d}   {y[0] or 0:6d} {diff} | {s['lh']:5d}  {y[1] or 0:5d}")
    trips = [r for r in rows if r["kind"] == "trip"]
    print(f"  trips {len(trips)}: " + "  ".join(f"{r['station']}+{r['last_hits']}({r['marches']}M{r.get('lasers', 0)}L,{r['seconds']}s,left {r['creeps_left']})" for r in trips))
    lands = [r for r in rows if r["kind"] == "landed"]
    stops = [round(b["clock"] - a["clock"], 1) for a, b in zip(lands, lands[1:]) if a["station"] == "F"]
    print("  fountain stops (land -> next landing, incl. 3 s Keen):", stops)
    dec = [r for r in rows if r["kind"] == "decision"]
    src = collections.Counter(r.get("src") for r in dec)
    diff = sum(1 for r in dec if r.get("src") == "jev" and r.get("pick") != r.get("rules"))
    print(f"  decisions {len(dec)}: {dict(src)}; Jev overruled the rules {diff}x")
    errs = collections.Counter((r.get("msg") or "")[-100:] for r in rows if r["kind"] == "error")
    other = collections.Counter(r["kind"] for r in rows if r["kind"] in ("stuck", "keen_failed", "wait_spawn", "retreat"))
    print("  errors:", errs.most_common(3) or "none", "| other:", dict(other) or "none")
    buys = [(round(r["clock"]), r["item"].replace("item_", "")) for r in rows if r["kind"] == "buy"]
    print("  buys:", buys)
    camp_check(rows)


def camp_check(rows):
    """Camps seen again after a :00 spawn: did the leftovers block it (Poke) or did a new set stack on top (7.41 notes)?"""
    seen = [r for r in rows if r["kind"] == "camp_seen" and r.get("last_seen") is not None and (r.get("spawns") or 0) >= 1]
    if not seen:
        print("  camp check: no camps seen again after a :00 spawn yet")
        return
    err = sum(abs(r["expected"] - r["actual"]) for r in seen) / len(seen)
    print(f"  camp check ({len(seen)} re-sightings): bot's guess off by {err:.1f} creeps per camp on average")
    for label, grp in (("left empty", [r for r in seen if r["last_seen"] == 0]),
                       ("left with creeps", [r for r in seen if r["last_seen"] > 0])):
        if grp:
            gain = sum((r["actual"] - r["last_seen"]) / r["spawns"] for r in grp) / len(grp)
            print(f"    {label:16s} {len(grp):3d}x: {gain:+.1f} creeps per :00 spawn  (about +4 = a new set spawned, about 0 = blocked)")


if __name__ == "__main__":
    if sys.argv[1:] == ["--camps"]:     # camp check over every run so far
        camp_check([json.loads(l) for f in glob.glob(os.path.join(HERE, "bot_runs", "*.jsonl")) for l in open(f, encoding="utf-8")])
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else None)
