"""Per-camp view of every Immortal camp trip: HP per camp at the first March, over time, and after leaving."""
import collections, csv, glob, json, math, os, statistics as st
D = "data/nhp"
CAMPS = {c["id"]: (c["x"], c["y"]) for c in json.load(open("data/transition.json"))["camps"]}
STANDS = {"A": (-2024, -3876), "C": (-4278, 98), "D": (-7586, -1147), "E": (-1632, -7720)}
def rd(p): return list(csv.DictReader(open(p, encoding="utf-8")))
def team_of(g):
    for r in rd(f"{D}/{g}_heroes.csv")[:60]:
        if r["hero"] == "Tinker": return int(r["team"])
    return 2
out = []
for f in sorted(glob.glob(f"{D}/*_neu.csv")):
    g = os.path.basename(f)[:-8]
    rv = (lambda x, y: (x, y)) if team_of(g) == 2 else (lambda x, y: (-x, -y))
    neu = rd(f)
    by_t = collections.defaultdict(dict)
    for r in neu: by_t[float(r["clock"])][r["idx"]] = r
    times = sorted(by_t)
    import bisect
    line = collections.defaultdict(list)
    for r in neu: line[r["idx"]].append((float(r["clock"]), int(r["hp"])))
    gone = {}
    for r in rd(f"{D}/{g}_spawn.csv"):
        if r["name"] == "gone": gone.setdefault(r["idx"], float(r["clock"]))
    def hp_of(i, t):
        if i in gone and gone[i] <= t: return 0
        L = line.get(i)
        if not L: return 0
        k = bisect.bisect_right(L, (t, 1e9)) - 1
        return L[k][1] if k >= 0 else L[0][1]
    def snap(t):
        i = min(range(len(times)), key=lambda k: abs(times[k] - t)) if times else None
        return by_t[times[i]] if i is not None and abs(times[i] - t) < 0.5 else {}
    casts = [r for r in rd(f"{D}/{g}_cast.csv") if 290 <= float(r["clock"]) <= 720]
    cur = []
    for c in casts + [{"ability": "keen_x", "clock": "99999"}]:
        if "keen" not in c["ability"]:
            cur.append(c); continue
        ms = [x for x in cur if "march" in x["ability"]]
        if ms:
            x0, y0 = float(ms[0]["x"]), float(ms[0]["y"]); rx, ry = rv(x0, y0)
            stn = min(STANDS, key=lambda k: math.hypot(STANDS[k][0] - rx, STANDS[k][1] - ry))
            if math.hypot(STANDS[stn][0] - rx, STANDS[stn][1] - ry) > 1300: stn = "other"
            t0 = float(ms[0]["clock"]); tl = float(c["clock"]) if c["clock"] != "99999" else float(cur[-1]["clock"]) + 1
            s0 = snap(t0 - 0.2)
            creeps = {}
            for idx, r in s0.items():
                px, py = rv(float(r["x"]), float(r["y"]))
                cid = min(CAMPS, key=lambda k: math.hypot(CAMPS[k][0] - px, CAMPS[k][1] - py))
                if math.hypot(CAMPS[cid][0] - px, CAMPS[cid][1] - py) < 900 and int(r["hp"]) > 0:
                    creeps[idx] = (cid, int(r["hp"]), r["name"])
            def hp_at(t):
                return {i: hp_of(i, t) for i in creeps}
            series = {dt: hp_at(t0 + dt) for dt in (3, 6, 9, 12)}
            last_m = float(ms[-1]["clock"])
            end = hp_at(max(tl, last_m) + 7)                      # after the last robots (6 s) are done
            per = collections.defaultdict(lambda: {"hp0": 0, "n": 0, "end": 0, "alive": 0, "hp": {3: 0, 6: 0, 9: 0, 12: 0}})
            for i, (cid, hp, nm) in creeps.items():
                p = per[cid]; p["hp0"] += hp; p["n"] += 1; p["end"] += end[i]; p["alive"] += end[i] > 0
                for dt in series: p["hp"][dt] += series[dt][i]
            camps = {cid: v for cid, v in per.items() if v["hp0"] - v["end"] >= 0.2 * v["hp0"]}    # targeted camps only
            out.append({"g": g, "st": stn, "t": t0, "lvl": int(ms[0]["level"]), "n_m": len(ms),
                        "n_l": sum("laser" in x["ability"] for x in cur), "on_site": round(tl - t0, 1),
                        "march_times": [round(float(m["clock"]) - t0, 1) for m in ms], "camps": camps})
        cur = []
json.dump(out, open("data/nhp_camptrips.json", "w"))
T = [t for t in out if t["st"] in "ACDE" and t["camps"]]
med = lambda v: round(st.median(v)) if v else "-"
print(len(out), "trips;", len(T), "with targeted camps")
for stn in "ACDE":
    for lo, hi, lab in ((1, 6, "March<=3"), (7, 30, "March 4")):
        X = [t for t in T if t["st"] == stn and lo <= t["lvl"] <= hi]
        if len(X) < 5: continue
        tot0 = [sum(c["hp0"] for c in t["camps"].values()) for t in X]
        cleared = sum(all(c["alive"] == 0 for c in t["camps"].values()) for t in X)
        print(f"\n{stn} {lab}: {len(X)} trips | targeted camps {st.mean([len(t['camps']) for t in X]):.1f}, HP {med(tot0)} "
              f"({med([sum(c['n'] for c in t['camps'].values()) for t in X])} creeps) | Marches {st.mean([t['n_m'] for t in X]):.1f} "
              f"Lasers {st.mean([t['n_l'] for t in X]):.2f} | on site {med([t['on_site'] for t in X])} s")
        for dt in (3, 6, 9, 12):
            print(f"   {dt:>2} s after 1st March: {med([100*sum(c['hp'][dt] for c in t['camps'].values())/max(1,sum(c['hp0'] for c in t['camps'].values())) for t in X])}% HP left")
        print(f"   after the robots are done: {med([100*sum(c['end'] for c in t['camps'].values())/max(1,sum(c['hp0'] for c in t['camps'].values())) for t in X])}% left; "
              f"all targeted camps dead in {100*cleared/len(X):.0f}% of trips; creeps left alive median {med([sum(c['alive'] for c in t['camps'].values()) for t in X])}")
