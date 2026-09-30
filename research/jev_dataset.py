"""Every Immortal 'where next?' moment (fountain landings 5:00-10:00) with the facts they had and what they did."""
import csv, json, math, statistics as st, collections, os
D = "data"
tr = json.load(open(f"{D}/transition.json")); T, camps = tr["games"], {c["id"]: c for c in tr["camps"]}
ST = {"A": {1, 2, 3, 7}, "C": {4, 5, 6}, "D": {23, 28, 32, 26, 18}, "E": {19, 21, 27}}
BLAND = (-964, -871)
def rows(g, k): return list(csv.DictReader(open(f"{D}/{g}_{k}.csv")))
def station(s):
    if s["where"] == "fountain": return "F"
    tot = collections.Counter()
    for c, n in s["camps"].items():
        for k, ids in ST.items():
            if int(c) in ids: tot[k] += n
    if tot: return tot.most_common(1)[0][0]
    return "B" if s["lane_kills"] >= 2 else "other"
out = []
for g, v in T.items():
    if g == "me": continue
    team = v["team"]
    snap, ev = rows(g, "snap"), rows(g, "events")
    start = float(snap[-1]["start"]); off = st.median(float(r["ts"]) - int(r["tick"]) / 30 for r in ev)
    clk = lambda t: int(t) / 30 + off - start
    S = [(clk(s["tick"]), float(s["mana"]), float(s["maxmana"]), int(s["level"])) for s in snap]
    ud = [(clk(r["tick"]), *((float(r["x"]), float(r["y"])) if team == 2 else (-float(r["x"]), -float(r["y"])))) for r in rows(g, "unitdeaths") if "Lane" in r["cls"]]
    steps = v["steps"]
    for i, s in enumerate(steps):
        if s["where"] != "fountain" or not (300 <= s["t"] < 600) or i + 1 >= len(steps): continue
        nxt = station(steps[i + 1])
        if nxt == "other": continue
        t = s["t"]
        snapx = min(S, key=lambda x: abs(x[0] - (t + 4)))           # mana as they leave fountain (~4 s later)
        m = int(t // 60)
        ready = {}
        for k in "ACDE":
            cleared = [p for p in steps[:i] if station(p) == k and int(p["t"] // 60) == m and sum(p["camps"].values()) >= 3]
            ready[k] = not cleared
        wave = sum(1 for (tt, x, y) in ud if t <= tt <= t + 25 and math.hypot(x - BLAND[0], y - BLAND[1]) < 1600)
        field = [p for p in steps[:i] if station(p) not in ("F", "other")]
        last = [{"to": station(p), "last_hits": sum(p["camps"].values()) + p["lane_kills"], "seconds": round(p["len"])} for p in field[-3:]]
        lvl = snapx[3]
        march = 4 if lvl >= 7 else 3 if lvl >= 5 else 2
        out.append({"game": g, "t": round(t, 1), "label": nxt, "state": {
            "game_clock": f"{int(t)//60}:{int(t)%60:02d}", "seconds_until_camps_respawn": 60 - int(t % 60),
            "tinker": {"location": "fountain", "level": lvl, "mana": int(snapx[1]), "max_mana": int(snapx[2]), "march_level": march},
            "camps": {k: {"ready": ready[k]} for k in "ACDE"},
            "mid_wave": {"visible": wave >= 2, "creeps_dying_there_soon": wave},
            "last_trips": last}})
json.dump(out, open(f"{D}/jev_station_set.json", "w"))
c = collections.Counter(o["label"] for o in out)
print(len(out), "decisions from", len({o['game'] for o in out}), "games; labels", dict(c))
print("with a wave visible, share picking B:", round(sum(o["label"] == "B" for o in out if o["state"]["mid_wave"]["visible"]) / max(1, sum(o["state"]["mid_wave"]["visible"] for o in out)), 2))
