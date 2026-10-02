"""The A geometry lab (python bot.py --lab 2 --lab-a 2): which stand spot + March facing kills the most at A.

    python a_lab_report.py [run.jsonl]       default: the latest run with geo lab results

Every test = both of A's real camps (north, south) with a family each, Tinker at a stand spot (tag: now = the bot's,
t<along>s<sideways> = on the camp-to-camp line, along from the north camp) facing `face`, at your March counts.
Score = bounty gold of what died (mean over reps and the two family sets); the baseline is tag now, face 325.
"""
import collections
import glob
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def latest():
    runs = [p for p in glob.glob(os.path.join(HERE, "bot_runs", "*.jsonl"))
            if '"lab_result"' in open(p, encoding="utf-8").read() and '"tag"' in open(p, encoding="utf-8").read()]
    return max(runs, key=os.path.getmtime)


def main(path=None):
    path = path or latest()
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    res = [r for r in rows if r.get("kind") == "lab_result" and r.get("tag")]
    print(f"{path}: {len(res)} tests")
    by = collections.defaultdict(list)
    for r in res:
        fam = "centaur+ogre" if any("centaur" in c for c in r["camp"]) else "satyr+wolf"
        north = sum(c["killed"] for c in r["camps"][0]["creeps"]) / len(r["camps"][0]["creeps"])
        south = sum(c["killed"] for c in r["camps"][1]["creeps"]) / len(r["camps"][1]["creeps"])
        by[(r["march"], r["marches"], fam, r["tag"], r["face"])].append((r["gold"], r["gold"] / max(r["gold_camp"], 1), north, south))
    for march, n in sorted({(k[0], k[1]) for k in by}):
        print(f"\n=== March {march}, {n} Marches + Laser (gold killed of both camps, mean of reps; both family sets averaged)")
        score = {}
        for (m, nn, fam, tag, face), v in by.items():
            if (m, nn) == (march, n):
                score.setdefault((tag, face), {})[fam] = (statistics.mean(x[0] for x in v), statistics.mean(x[1] for x in v),
                                                          statistics.mean(x[2] for x in v), statistics.mean(x[3] for x in v), len(v))
        table = []
        for (tag, face), d in score.items():
            if len(d) < 2:
                continue
            table.append((statistics.mean(x[0] for x in d.values()), statistics.mean(x[1] for x in d.values()),
                          statistics.mean(x[2] for x in d.values()), statistics.mean(x[3] for x in d.values()),
                          sum(x[4] for x in d.values()), tag, face))
        table.sort(reverse=True)
        base = next((t for t in table if t[5] == "now" and t[6] == 325), None)
        print("   gold   %gold  north  south   n   spot   face")
        for t in table[:12]:
            print(f" {t[0]:6.0f}  {t[1]*100:4.0f}%  {t[2]*100:4.0f}%  {t[3]*100:4.0f}%  {t[4]:3d}   {t[5]:8} {t[6]:3d}")
        if base:
            rank = table.index(base) + 1
            print(f" baseline (now, 325): {base[0]:.0f} gold {base[1]*100:.0f}%, north {base[2]*100:.0f}% south {base[3]*100:.0f}%, "
                  f"rank {rank} of {len(table)}")
        print(" best facing per spot:")
        best = {}
        for t in table:
            if t[5] not in best:
                best[t[5]] = t
        for tag, t in sorted(best.items(), key=lambda kv: -kv[1][0]):
            print(f"   {tag:8} face {t[6]:3d}: {t[0]:5.0f} gold ({t[1]*100:.0f}%)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
