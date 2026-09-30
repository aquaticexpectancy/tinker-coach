"""Reconstruct the laning->jungle transition (3:30-10:00) of every game in radiant view."""
import csv, collections, json, math, os, statistics

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data")
M = json.load(open(os.path.join(D, "metrics.json")))
CODE = {"march_of_the_machines": "M", "rearm": "R", "laser": "L", "item_blink": "B", "item_bottle": "b",
        "deploy_turrets": "D", "keen_teleport": "K"}


def rows(p, kind):
    with open(os.path.join(D, f"{p}_{kind}.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def rv(team, x, y):
    return (x, y) if team == 2 else (-x, -y)


# --- shared camp list (radiant view) from every game's spawns -------------------
games = list(M.keys())
clk_of, team_of = {}, {}
for g in games:
    snap, ev = rows(g, "snap"), rows(g, "events")
    start = float(snap[-1]["start"])
    off = statistics.median(float(r["ts"]) - int(r["tick"]) / 30 for r in ev)
    clk_of[g] = (start, off)
    team_of[g] = M[g]["team"]

pts = []
for g in games:
    start, off = clk_of[g]
    for r in rows(g, "spawns"):
        if int(r["tick"]) / 30 + off - start > 50:
            pts.append(rv(team_of[g], float(r["x"]), float(r["y"])))
cl = []
for x, y in pts:
    for c in cl:
        if math.hypot(c["x"] - x, c["y"] - y) < 650:
            c["n"] += 1; c["sx"] += x; c["sy"] += y; c["x"] = c["sx"] / c["n"]; c["y"] = c["sy"] / c["n"]; break
    else:
        cl.append({"x": x, "y": y, "n": 1, "sx": x, "sy": y})
camps = [c for c in cl if c["n"] >= 40]
# keep own-side camps (radiant half) + a few river ones; number by distance from mid-lane radiant T1 (-1600,-1400)
for c in camps:
    c["own"] = c["x"] + c["y"] < 0
camps.sort(key=lambda c: math.hypot(c["x"] + 1600, c["y"] + 1400))
for i, c in enumerate(camps):
    c["id"] = i + 1
print("camps", [(c["id"], int(c["x"]), int(c["y"]), c["own"], c["n"]) for c in camps])


def camp_at(x, y, r=1000):
    c = min(camps, key=lambda c: math.hypot(c["x"] - x, c["y"] - y))
    return c["id"] if math.hypot(c["x"] - x, c["y"] - y) < r else None


def lane_of(x, y):
    if x < -5200 and y < -4600: return "base"
    if abs(x - y) < 1600: return "mid"
    if x < -5000 or y > 5200: return "top"
    if x > 5000 or y < -5200: return "bot"
    return "river/jungle"


out = {}
for g in games:
    team = team_of[g]
    kills = [(t, k, n, *rv(team, x, y)) for t, k, n, x, y in M[g]["kills"]]
    path = [(t, *rv(team, x, y), life) for t, x, y, life in M[g]["path"]]
    start, off = clk_of[g]
    ev = rows(g, "events")
    casts = [(int(r["tick"]) / 30 + off - start, r["inflictor"].replace("tinker_", ""), *rv(team, float(r["tx"]), float(r["ty"])))
             for r in ev if r["type"] in ("ABILITY", "ITEM") and "tinker" in r["attacker"]]
    at = lambda t: min(path, key=lambda s: abs(s[0] - t))
    # camp name per camp id from creeps killed there
    names = collections.defaultdict(collections.Counter)
    for t, k, n, x, y in kills:
        if k == "N":
            cid = camp_at(x, y)
            if cid: names[cid][n] += 1
    # trips 3:30-10:00 built from landings (position jump > 1200 after a Keen cast)
    keens = [c[0] for c in casts if c[1] == "keen_teleport"]
    lands = []
    for i, tk in enumerate(keens):
        nxt = keens[i + 1] if i + 1 < len(keens) else tk + 15
        o = at(tk)
        land = next((s for s in path if tk < s[0] <= nxt + 1 and math.hypot(s[1] - o[1], s[2] - o[2]) > 1200), None)
        if land: lands.append(land)
    steps = []
    # pre-Keen: marches cast from lane that killed neutrals
    pre = [(t, k, n, x, y) for t, k, n, x, y in kills if k == "N" and t < (lands[0][0] if lands else 600)]
    for i, l in enumerate(lands):
        t0 = l[0]; t1 = lands[i + 1][0] if i + 1 < len(lands) else t0 + 20
        if t0 > 600: break
        kk = [k for k in kills if t0 <= k[0] < t1 + 2]
        where = "fountain" if lane_of(l[1], l[2]) == "base" else None
        cids = collections.Counter(camp_at(k[3], k[4]) for k in kk if k[1] == "N")
        lane_k = sum(1 for k in kk if k[1] == "L")
        land_camp = camp_at(l[1], l[2], 1400)
        seq = "".join(CODE.get(c[1].replace("item_", "item_"), "") for c in casts if t0 - 0.5 < c[0] < t1)
        marches = [(round(c[0], 1), round(c[2]), round(c[3])) for c in casts if t0 - 0.5 < c[0] < t1 and c[1] == "march_of_the_machines"]
        steps.append({"t": round(t0, 1), "len": round(t1 - t0, 1), "land": [round(l[1]), round(l[2])],
                      "where": where or (f"camp {land_camp}" if land_camp else lane_of(l[1], l[2])),
                      "camps": {str(k): v for k, v in cids.items() if k}, "lane_kills": lane_k, "seq": seq,
                      "marches": marches, "level": at(t0 + 1)[0] and None})
    snaps = {m: M[g]["permin"][str(m)] for m in (5, 6, 7, 8, 9, 10)}
    out[g] = {"team": team, "pre_keen_neutral": len(pre), "pre_camps": dict(collections.Counter(camp_at(k[3], k[4]) for k in pre)),
              "first_keen": M[g]["first_keen"], "first_neu": M[g]["first_neutral_after_keen"], "first_anc": M[g]["first_ancient"],
              "nw10": M[g]["permin"]["10"]["nw"], "neu7": M[g]["permin"]["7"]["neu"], "neu10": M[g]["permin"]["10"]["neu"],
              "lvl8": M[g]["permin"]["8"]["lvl"], "steps": steps, "camp_names": {str(k): v.most_common(2) for k, v in names.items()},
              "permin": snaps}

json.dump({"camps": [{"id": c["id"], "x": c["x"], "y": c["y"], "own": c["own"]} for c in camps], "games": out},
          open(os.path.join(D, "transition.json"), "w"))

rank = sorted([g for g in games if g != "me"], key=lambda g: (out[g]["neu10"]), reverse=True)
for g in rank[:8] + ["me"]:
    o = out[g]
    fmt = lambda t: "—" if t is None else f"{int(t//60)}:{int(t%60):02d}"
    print(f"\n### {g} team {o['team']} keen {fmt(o['first_keen'])} 1stN {fmt(o['first_neu'])} anc {fmt(o['first_anc'])} neu7 {o['neu7']} neu10 {o['neu10']} nw10 {o['nw10']} preN {o['pre_keen_neutral']} {o['pre_camps']}")
    for s in o["steps"]:
        if s["t"] < 280: continue
        print(f"  {fmt(s['t'])} {s['len']:5.1f}s {s['where']:12s} {s['seq']:18s} camps {s['camps']} lane {s['lane_kills']}")
