"""The March lab's table: what each sequence kills, per station, camp family (pair) and March level.

    python lab_report.py                 latest lab run in bot_runs/
    python lab_report.py <run.jsonl>
    python lab_report.py --csv           also write lab_table.csv (one row per family x March level x sequence)

For every family (or pair of families at two-camp stations) and March level: creeps killed by 1-4 Marches, with
and without a Laser after the last one, and the cheapest sequence that clears the camp. Every extra March costs
~4 s (a Rearm channel and the recast).
"""
import collections
import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHORT = {"polar_furbolg": "furbolg", "centaur_": "centaur ", "satyr_": "satyr ", "forest_troll_": "troll ",
         "_thunder_lizard": " lizard", "frostbitten_golem": "frost golem", "warpine_raider": "warpine",
         "kobold_": "kobold ", "gnoll_assassin": "gnoll", "black_dra": "dra"}


def short(family):
    out = family
    for a, b in SHORT.items():
        out = out.replace(a, b)
    return out


def load(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("kind") == "lab_result":
            rows.append(r)
    return rows


def main(args):
    write_csv = "--csv" in args
    args = [a for a in args if a != "--csv"]
    path = args[0] if args else max((p for p in glob.glob(os.path.join(HERE, "bot_runs", "*.jsonl"))
                                     if '"lab_result"' in open(p, encoding="utf-8").read()), key=os.path.getmtime)
    rows = load(path)
    print(f"{os.path.basename(path)}: {len(rows)} lab tests")
    by = collections.defaultdict(dict)
    for r in rows:
        combo = " + ".join(c["family"] for c in r["camps"])
        by[(r["station"], r["march"], combo)][(r["marches"], r["laser"])] = r
    table = []
    plans = [(n, l) for l in (0, 1) for n in (1, 2, 3, 4)]
    for st in "ACDE":
        for ml in (3, 4):
            combos = sorted(k for k in by if k[0] == st and k[1] == ml)
            if not combos:
                continue
            print(f"\n{st} at March {ml}: killed per sequence (M = Marches, +L = then a Laser); first clear marked *")
            print("   " + " ".join(f"{n}M{'+L' if l else '  '}" for n, l in plans) + "   family")
            for key in combos:
                res = by[key]
                cells, first = [], None
                for n, l in plans:
                    r = res.get((n, l))
                    if not r:
                        cells.append("  .  ")
                        continue
                    clear = not r["left"]
                    if clear and first is None:
                        first = (n, l)
                    cells.append(f"{r['killed']:2d}/{r['creeps']:<2d}" + ("*" if clear else " "))
                    table.append({"station": st, "march": ml, "family": key[2], "marches": n, "laser": l,
                                  "creeps": r["creeps"], "killed": r["killed"], "cleared": clear,
                                  "left": ";".join(f"{x['name']}:{x['hp']}" for x in r["left"])})
                best = f"{first[0]}M{'+L' if first[1] else ''}" if first else "never"
                print("   " + " ".join(cells) + f"   {short(key[2])}  -> {best}")
    if write_csv and table:
        with open(os.path.join(HERE, "lab_table.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(table[0]))
            w.writeheader()
            w.writerows(table)
        print("\n-> lab_table.csv")


if __name__ == "__main__":
    main(sys.argv[1:])
