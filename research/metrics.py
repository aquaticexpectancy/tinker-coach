"""Per-game Tinker farming metrics for every parsed replay -> data/metrics.json."""
import csv, collections, json, math, os, statistics, sys

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
ANCIENTS = ("black_drake", "black_dragon", "thunder_lizard", "granite_golem", "rock_golem",
            "prowler", "frostbitten", "ice_shaman", "elder_jungle")
CODE = {"march_of_the_machines": "M", "rearm": "R", "laser": "L", "item_blink": "B", "item_bottle": "b",
        "deploy_turrets": "D", "warp_grenade": "W", "keen_teleport": "K"}


def rows(p, kind):
    with open(os.path.join(D, f"{p}_{kind}.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def in_base(x, y):
    return (x < -5200 and y < -4600) or (x > 4600 and y > 4000)


def camps_of(sp, clk):
    cl = []
    for r in sp:
        if clk(r["tick"]) <= 50:
            continue
        x, y = float(r["x"]), float(r["y"])
        for c in cl:
            if math.hypot(c[0] - x, c[1] - y) < 500:
                c[2] += 1; c[3] += x; c[4] += y; c[0] = c[3] / c[2]; c[1] = c[4] / c[2]; break
        else:
            cl.append([x, y, 1, x, y])
    return [(c[0], c[1]) for c in cl if c[2] >= 6]


def analyse(p):
    snap, ev, ud, sp = rows(p, "snap"), rows(p, "events"), rows(p, "unitdeaths"), rows(p, "spawns")
    heroes = rows(p, "heroes")
    start = float(snap[-1]["start"])
    off = statistics.median(float(r["ts"]) - int(r["tick"]) / 30 for r in ev)
    clk = lambda tick: int(tick) / 30 + off - start
    team = int([h for h in heroes if "Tinker" in h["cls"]][0]["team"])
    own = (lambda x, y: x + y < 0) if team == 2 else (lambda x, y: x + y > 0)
    S = [(clk(s["tick"]), float(s["x"]), float(s["y"]), int(s["lh"]), int(s["nw"]), int(s["level"]),
          float(s["mana"]), float(s["maxmana"]), int(s["life"]), int(s["campsStacked"]), int(s["neutralGold"]),
          int(s["creepGold"])) for s in snap]
    camps = camps_of(sp, clk)

    # join combat-log deaths (who/what) to entity deaths (where)
    pool = collections.defaultdict(list)
    for u in ud:
        pool[int(u["tick"])].append(u)
    kills = []
    for d in ev:
        if d["type"] != "DEATH" or "tinker" not in d["attacker"]:
            continue
        tgt = d["target"]
        kind = "N" if tgt.startswith("npc_dota_neutral") else ("L" if ("creep" in tgt or "siege" in tgt) else None)
        if not kind:
            continue
        t = int(d["tick"]); m = None
        for dt in (0, 1, -1, 2, -2, 3):
            c = [u for u in pool.get(t + dt, []) if ("Neutral" if kind == "N" else "Lane") in u["cls"]]
            if c:
                m = c[0]; pool[t + dt].remove(m); break
        if m:
            x, y = float(m["x"]), float(m["y"])
            kills.append((clk(t), kind, tgt.replace("npc_dota_neutral_", ""), x, y, own(x, y)))
    casts = [(clk(r["tick"]), r["inflictor"].replace("tinker_", ""), float(r["tx"]), float(r["ty"]))
             for r in ev if r["type"] in ("ABILITY", "ITEM") and "tinker" in r["attacker"]]
    deaths = [clk(r["tick"]) for r in ev if r["type"] == "DEATH" and r["target"] == "npc_dota_hero_tinker"]

    def at(t):
        return min(S, key=lambda s: abs(s[0] - t))

    permin = {}
    for m in range(0, 21):
        s = at(m * 60)
        permin[m] = {"lh": s[3], "nw": s[4], "lvl": s[5], "neu": s[10], "lane": s[11], "stack": s[9]}

    def cnt(name, a, b):
        return sum(1 for c in casts if c[1] == name and a <= c[0] < b)

    def nk(a, b, kind=None):
        return sum(1 for k in kills if a <= k[0] < b and (kind is None or k[1] == kind))

    keen = [c[0] for c in casts if c[1] == "keen_teleport"]
    first = lambda cond: next((k[0] for k in kills if cond(k)), None)
    # fountain visits 5-20
    visits, inb = [], False
    for s in S:
        if not (300 <= s[0] < 1200):
            continue
        b = in_base(s[1], s[2]) and s[8] == 0
        if b and not inb:
            visits.append([s[0], s[0]])
        if b:
            visits[-1][1] = s[0]
        inb = b
    dwell = [v[1] - v[0] + 0.5 for v in visits]
    # trips between Keen Teleports
    # A trip starts when Tinker actually lands (position jumps > 1200 after a Keen cast)
    # and lasts until the next landing, so it covers everything done at that spot.
    landings = []
    for i, tk in enumerate(keen):
        nxt = keen[i + 1] if i + 1 < len(keen) else tk + 15
        o = at(tk)
        land = next((s for s in S if tk < s[0] <= nxt + 1 and math.hypot(s[1] - o[1], s[2] - o[2]) > 1200), None)
        if land:
            landings.append(land)
    trips = []
    for i, land in enumerate(landings):
        t0 = land[0]
        t1 = landings[i + 1][0] if i + 1 < len(landings) else t0 + 20
        if not (300 <= t0 < 1200):
            continue
        fount = in_base(land[1], land[2])
        seq = "".join(CODE.get(c[1], "") for c in casts if t0 - 0.5 < c[0] < t1)
        k = nk(t0, t1 + 2)
        rearm_t = next((c[0] for c in casts if t0 - 0.5 < c[0] < t1 and c[1] == "rearm"), None)
        bottles_before = sum(1 for c in casts if t0 - 0.5 < c[0] < (rearm_t or t1) and c[1] == "item_bottle")
        trips.append({"t": t0, "len": t1 - t0, "fountain": fount, "kills": k, "seq": seq,
                      "to_rearm": (rearm_t - t0) if rearm_t else None, "bottles_before": bottles_before,
                      "marches": seq.count("M"), "blink_open": seq.startswith("B")})
    farm_trips = [t for t in trips if not t["fountain"]]
    kt = sorted(k[0] for k in kills if 300 <= k[0] < 1200)
    gaps = sorted((b - a for a, b in zip(kt, kt[1:])), reverse=True)
    blink = next((c[0] for c in casts if c[1] == "item_blink"), None)
    mid_share = sum(1 for s in S if 90 <= s[0] < 300 and abs(s[1] - s[2]) < 1600) / max(1, sum(1 for s in S if 90 <= s[0] < 300))
    lowmana = sum(0.5 for s in S if 300 <= s[0] < 1200 and s[8] == 0 and s[6] < 0.2 * s[7])
    dead = sum(0.5 for s in S if 300 <= s[0] < 1200 and s[8] != 0)
    nk15 = nk(300, 900, "N")
    return {
        "game": p, "team": team, "mid_share": round(mid_share, 2), "permin": permin,
        "first_keen": keen[0] if keen else None,
        "first_neutral": first(lambda k: k[1] == "N" and k[0] > 0),
        "first_neutral_after_keen": first(lambda k: k[1] == "N" and keen and k[0] >= keen[0]),
        "first_ancient": first(lambda k: k[1] == "N" and any(a in k[2] for a in ANCIENTS)),
        "ancient_kills_20": sum(1 for k in kills if k[0] < 1200 and k[1] == "N" and any(a in k[2] for a in ANCIENTS)),
        "kpm_5_10": nk(300, 600) / max(1, cnt("march_of_the_machines", 300, 600)),
        "kpm_10_15": nk(600, 900) / max(1, cnt("march_of_the_machines", 600, 900)),
        "kpm_5_20": nk(300, 1200) / max(1, cnt("march_of_the_machines", 300, 1200)),
        "marches_5_20": cnt("march_of_the_machines", 300, 1200), "rearms_5_20": cnt("rearm", 300, 1200),
        "keen_5_20": cnt("keen_teleport", 300, 1200), "lasers_5_20": cnt("laser", 300, 1200),
        "bottle_5_20": cnt("item_bottle", 300, 1200), "blink_first": blink,
        "blink_nw": at(blink)[4] if blink else None,
        "turrets_first": next((c[0] for c in casts if c[1] == "deploy_turrets"), None),
        "kills_5_10": nk(300, 600), "kills_10_15": nk(600, 900), "kills_15_20": nk(900, 1200),
        "neutral_share_5_15": nk15 / max(1, nk(300, 900)),
        "enemy_side_neutral_share_5_20": sum(1 for k in kills if 300 <= k[0] < 1200 and k[1] == "N" and not k[5]) / max(1, nk(300, 1200, "N")),
        "base_time_5_20": sum(dwell), "base_visits_5_20": len(visits), "avg_dwell": statistics.mean(dwell) if dwell else None,
        "median_dwell": statistics.median(dwell) if dwell else None,
        "farm_trips_5_20": len(farm_trips), "empty_trips_5_20": sum(1 for t in farm_trips if t["kills"] == 0),
        "kills_per_farm_trip": statistics.mean(t["kills"] for t in farm_trips) if farm_trips else None,
        "avg_trip_len": statistics.mean(t["len"] for t in farm_trips) if farm_trips else None,
        "gap_top3": gaps[:3], "gaps_over_40": sum(1 for g in gaps if g > 40),
        "lowmana_5_20": lowmana, "dead_5_20": dead, "deaths_20": sum(1 for d in deaths if d < 1200),
        "stacks_20": permin[20]["stack"],
        "fountain_len": statistics.median(t["len"] for t in trips if t["fountain"]) if any(t["fountain"] for t in trips) else None,
        "fountain_to_rearm": statistics.median(t["to_rearm"] for t in trips if t["fountain"] and t["to_rearm"]) if any(t["fountain"] and t["to_rearm"] for t in trips) else None,
        "fountain_bottles_before_rearm": statistics.mean(t["bottles_before"] for t in trips if t["fountain"]) if any(t["fountain"] for t in trips) else None,
        "marches_per_farm_trip": statistics.mean(t["marches"] for t in farm_trips) if farm_trips else None,
        "blink_open_share_10_20": (lambda ts: sum(t["blink_open"] for t in ts) / len(ts) if ts else None)([t for t in farm_trips if t["t"] >= 600]),
        "trip_seqs": [t["seq"] for t in farm_trips],
        "fountain_seqs": [t["seq"] for t in trips if t["fountain"]],
        "camps": camps,
        "kills": [k[:5] for k in kills if k[0] < 1200],
        "path": [(round(s[0], 1), round(s[1]), round(s[2]), s[8]) for s in S if s[0] < 1200],
    }


if __name__ == "__main__":
    games = ["me", "pro"] + sorted(f[:-9] for f in os.listdir(D) if f[:2] in ("p9", "s9") and f.endswith("_snap.csv"))
    out = {}
    for g in games:
        try:
            out[g] = analyse(g)
            m = out[g]
            print(f"{g:12s} mid {m['mid_share']:.2f} lh10 {m['permin'][10]['lh']:3d} nw10 {m['permin'][10]['nw']:5d} nw15 {m['permin'][15]['nw']:5d} "
                  f"lvl10 {m['permin'][10]['lvl']:2d} neu10 {m['permin'][10]['neu']:4d} 1stN {m['first_neutral_after_keen'] or -1:5.0f} "
                  f"anc {m['first_ancient'] or -1:5.0f} kpm {m['kpm_5_20']:.2f} base {m['base_time_5_20']:.0f} dwell {m['median_dwell'] or 0:.1f} "
                  f"empty {m['empty_trips_5_20']}/{m['farm_trips_5_20']} d20 {m['deaths_20']}")
        except Exception as e:
            print(g, "ERROR", repr(e))
    json.dump(out, open(os.path.join(D, "metrics.json"), "w"))
