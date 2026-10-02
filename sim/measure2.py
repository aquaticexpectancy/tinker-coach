"""Part 2 of measure.py: payoffs, camps and respawn, waves, progression, the user's own runs."""
import os, json, math, collections, statistics as st, csv
from load import *
from trips import trips_of

PASSIVE = 1000.0 / 700.0       # checked below against the logs
PAYOFF_SETUPS = {"lab_10x", "lab", "user", "a3_10x", "brute4_10x", "af300_10x", "af0_10x", "pull_10x", "awake_10x",
                 "rules_facing", "rate_mana", "rules_mana", "rate", "tricks", "rules_fresh",
                 "force1_10x", "force2_10x", "force3_10x", "force4_10x"}
CAMPS = {"A": [(-1454, -3357), (-1983, -4815)], "C": [(-4013, 991), (-5015, -96)],
         "D": [(-8023, -1838), (-8314, -553)], "E": [(-721, -7696)]}
TRACKED = {"A": [0], "C": [0, 1], "D": [0, 1], "E": [0]}      # the bot's own camp list (camp_spot events: the others had no spawner)


def ms(v):
    v = [x for x in v if x is not None]
    return (st.mean(v), st.pstdev(v), len(v)) if v else (0, 0, 0)


def assign(creeps, S, R=700):
    out = [0] * len(CAMPS[S])
    for c in creeps:
        d = [math.hypot(c[4] - x, c[5] - y) for x, y in CAMPS[S]]
        i = min(range(len(d)), key=lambda j: d[j])
        if d[i] < R:
            out[i] += 1
    return out


def run(P, md, lab_runs, lt, idx):
    # ---------------------------------------------------------------- passive gold
    d = []
    for n in lab_runs[:50]:
        ev = read_run(n)
        sn = [e for e in ev if e["kind"] == "snap" and e["clock"] >= 297.4]
        buys = [e["clock"] for e in ev if e["kind"] == "buy"]
        for a, b in zip(sn, sn[1:]):
            if abs(b["clock"] - a["clock"] - 1) > .05 or b["lh"] != a["lh"]:
                continue
            if any(a["clock"] - .2 <= x <= b["clock"] + .2 for x in buys):
                continue
            if abs(b["gold"] - a["gold"]) <= 3:
                d.append(b["gold"] - a["gold"])
    P["passive_gold_per_s"] = round(st.mean(d), 4)
    md("\n## Gold\n")
    md("passive gold: %.3f / s without a kill (the bot ticks +1 every 0.7 s = 1.429), n=%d one-second windows" % (st.mean(d), len(d)))

    # ---------------------------------------------------------------- payoff records (all comparable setups)
    recs = []
    runs_used = collections.Counter()
    for n, s in idx.items():
        if s not in PAYOFF_SETUPS:
            continue
        ev = read_run(n)
        ds = [e for e in ev if e["kind"] == "drill_start"]
        if not ds or ds[0]["state"] != "2026-09-29_1851 at 5:00" or not any(e["kind"] == "end" for e in ev):
            continue
        runs_used[s] += 1
        last = {}
        for t in trips_of(ev):
            S = t["station"]
            if t["lh"] is None or t["nw_next"] is None or t["t_next_out"] is None:
                continue
            M = None
            if S in last:
                M = min(int(t["t_land"] // 60) - int(last[S] // 60), 2)
            last[S] = t["t_land"]
            bounty = t["nw_next"] - t["nw_land"] - P["passive_gold_per_s"] * (t["t_next_out"] - t["t_land"])
            recs.append({"S": S, "N": t["n_march"], "L": t["n_laser"], "ml": t["march_level"], "M": M if M is not None else 2,
                         "first": M is None, "lh": t["lh"], "gold": round(bounty, 1), "setup": s, "run": n,
                         "arrive": t["n_arrive"], "t": round(t["t_land"], 1), "wave": t["wave"],
                         "t_dur": round(t["t_next_out"] - t["t_land"], 1),
                         "tail": round(t["t_home"] - (max(t["march_times"]) if t["march_times"] else t["t_land"]), 2) if t["t_home"] else None,
                         "walk": round(t["t_first_march"] - t["t_land"], 2) if t["t_first_march"] else None})
    P["payoff_records"] = recs
    md("\n## Payoff per trip (%d trips from %d games: %s)\n" % (len(recs), sum(runs_used.values()), dict(runs_used)))
    md("bounty = net-worth gain from landing to the next Keen-out minus passive gold; first visits count as M>=2 (full camps).\n")
    md("| station | Marches | March lvl | n | LH mean (sd) | bounty gold mean (sd) | gold / LH |\n|---|---|---|---|---|---|---|")
    by = collections.defaultdict(list)
    for r in recs:
        by[(r["S"], r["N"], r["ml"])].append(r)
    for k in sorted(by):
        v = by[k]
        if len(v) < 5:
            continue
        lh = ms([r["lh"] for r in v]); g = ms([r["gold"] for r in v])
        md("| %s | %d | %d | %d | %.2f (%.2f) | %.0f (%.0f) | %.1f |" % (k[0], k[1], k[2], len(v), lh[0], lh[1], g[0], g[1], g[0] / max(lh[0], .01)))
    md("\nPer-trip LH by number of :00 marks since the station's last visit (M; 'first' = never visited), camps only, 3 Marches at March 3 / 2-3 at March 4:\n")
    md("| station | first visit | M=0 | M=1 | M>=2 |\n|---|---|---|---|---|")
    for S in "ACDE":
        cells = []
        for key in ("first", 0, 1, 2):
            v = [r["lh"] for r in recs if r["S"] == S and r["N"] >= 2 and ((r["first"]) if key == "first" else (not r["first"] and r["M"] == key))]
            cells.append("%.2f (n=%d)" % (st.mean(v), len(v)) if v else "-")
        md("| %s | %s |" % (S, " | ".join(cells)))
    P["gold_per_lh"] = {S: round(st.mean([r["gold"] for r in recs if r["S"] == S and r["lh"] > 0]) / st.mean([r["lh"] for r in recs if r["S"] == S and r["lh"] > 0]), 2) for S in "ABCDE"}

    # ---------------------------------------------------------------- March-count shape from the controlled lab (assumption fill)
    lab = collections.defaultdict(list)
    for r in csv.DictReader(open(os.path.join(ROOT, "lab_table.csv"), encoding="utf-8")):
        if r["laser"] == "0":
            lab[(r["station"], int(r["march"]), int(r["marches"]))].append(int(r["killed"]) / max(1, int(r["creeps"])))
    ratio = {}
    md("\n## March-count shape from lab_table.csv (controlled lab, no Laser): kill fraction relative to 3 Marches\n")
    md("| station | March lvl | 1 | 2 | 3 | 4 | n per cell |\n|---|---|---|---|---|---|---|")
    for S in "ACD":
        ratio[S] = {}
        for ml in (3, 4):
            base3 = st.mean(lab[(S, ml, 3)]) or 1e-9
            ratio[S][str(ml)] = {str(N): round(st.mean(lab[(S, ml, N)]) / base3, 3) for N in (1, 2, 3, 4)}
            md("| %s | %d | %s | %d |" % (S, ml, " | ".join("%.2f" % ratio[S][str(ml)][str(N)] for N in (1, 2, 3, 4)), len(lab[(S, ml, 3)])))
    ratio["E"] = {str(ml): {str(N): round(st.mean(ratio[S][str(ml)][str(N)] for S in "ACD"), 3) for N in (1, 2, 3, 4)} for ml in (3, 4)}
    md("(E: the lab's E is not like the real E, so E uses the mean of A, C, D. These ratios are an ASSUMPTION wherever the real trips have no data: Marches 1 and 4 at A, C, D, E.)")
    P["n_ratio"] = ratio

    # ---------------------------------------------------------------- camps: full sizes, leftover and respawn
    first = collections.defaultdict(list)
    arrive_by_M = collections.defaultdict(list)
    prev = {}
    for n in lab_runs:
        ev = read_run(n)
        g = collections.defaultdict(list)
        for e in ev:
            if e["kind"] == "trip_creeps":
                g[(e["station"], e["start"])].append(e)
        seen = set()
        last_end = {}
        for (S, start), lst in sorted(g.items(), key=lambda kv: kv[0][1]):
            if S not in CAMPS:
                continue
            lst.sort(key=lambda e: e["dt"])
            a = assign(lst[0]["creeps"], S)
            if S not in seen:
                seen.add(S)
                first[S].append(a)
            else:
                M = min(int(start // 60) - int(last_end[S] // 60), 2)
                arrive_by_M[(S, M)].append(sum(a))
            last_end[S] = start
    full = {}
    md("\n## Camps: creeps on first look (full set), per physical camp (spawner positions)\n")
    md("| station | camp | tracked by the bot | full set mean (sd) | n |\n|---|---|---|---|---|")
    for S in "ACDE":
        full[S] = []
        for ci in range(len(CAMPS[S])):
            v = [x[ci] for x in first[S]]
            m = st.mean(v)
            full[S].append(round(m, 2))
            md("| %s | %d (%d,%d) | %s | %.2f (%.2f) | %d |" % (S, ci, CAMPS[S][ci][0], CAMPS[S][ci][1], "yes" if ci in TRACKED[S] else "no", m, st.pstdev(v), len(v)))
    P["camps"] = {"positions": CAMPS, "tracked": TRACKED, "full": full,
                  "first_total": {S: ms([sum(x) for x in first[S]])[0] for S in "ACDE"}}
    md("\nCreeps standing at a station when Tinker lands again, by :00 marks since the last landing there (all camps of the station):\n")
    md("| station | first | M=0 | M=1 | M>=2 |\n|---|---|---|---|---|")
    arr = {}
    for S in "ACDE":
        cells = ["%.1f" % st.mean(sum(x) for x in first[S])]
        for M in (0, 1, 2):
            v = arrive_by_M[(S, M)]
            cells.append("%.1f (n=%d)" % (st.mean(v), len(v)) if v else "-")
            arr[(S, M)] = st.mean(v) if v else None
        md("| %s | %s |" % (S, " | ".join(cells)))
    # p_leak: how often a camp holding leftovers gets a fresh set at :00
    pl = []
    for S in "ACDE":
        f = P["camps"]["first_total"][S]
        m0, m1, m2 = arr[(S, 0)], arr[(S, 1)], arr[(S, 2)]
        if m0 and m1 and f > m0:
            pl.append((S, (m1 - m0) / (f - m0)))
    P["camps"]["leak_per_minute_by_station"] = {S: round(max(0.0, min(1.0, x)), 3) for S, x in pl}
    P["camps"]["leak_per_minute"] = round(st.mean(x for _, x in pl), 3)
    md("\nA camp that still holds leftovers at :00 gets a fresh set with probability (arrival(M=1)-arrival(M=0)) / (full-arrival(M=0)): %s; an empty camp refills at :00 (always)." % {S: round(x, 2) for S, x in pl})
    # what the bot sees after a trip (Book at +3.5 s after landing home) vs what is really there at the next landing (M=0)
    ls = []; act = []
    for n in lab_runs:
        for e in read_run(n):
            if e["kind"] == "camp_seen" and e.get("last_seen") is not None and e.get("spawns") == 0:
                ls.append(e["last_seen"]); act.append(e["actual"])
    el = [t["creeps_left"] for t in lt if t["station"] == "E" and t["creeps_left"] is not None]
    P["camps"]["left_after_trip_override"] = {"E": el}
    md("\nE (frogs split when they die): the bot books %.1f creeps left after every E trip (n=%d), so E stays blocked and the bot goes to E once per game (95 of 95 games); the simulator keeps these counts as E's leftovers." % (st.mean(el), len(el)))
    P["camps"]["booked_vs_real_same_minute"] = {"booked_mean": round(st.mean(ls), 2), "real_mean": round(st.mean(act), 2), "n": len(ls)}
    md("what the bot books as left after a trip (3.5 s after landing home) vs what is there when it lands again in the same minute: %.2f vs %.2f (n=%d); creeps still chasing are outside its 650 count." % (st.mean(ls), st.mean(act), len(ls)))

    # ---------------------------------------------------------------- waves
    dec = []
    for n in lab_runs:
        for e in read_run(n):
            if e["kind"] == "decision" and e.get("what") == "station" and e["options"] != ["F"] and e.get("wave") is not None and not e.get("prefetched"):
                dec.append((e["clock"], e["wave"]))
    wv = {}
    md("\n## Mid wave (decisions in lab_10x, n=%d): enemy lane creeps in reach of the B landing, by game-clock mod 30\n" % len(dec))
    md("| phase (s) | P(wave seen) | creeps when seen | n |\n|---|---|---|---|")
    for lo in range(0, 30, 2):
        v = [w for c, w in dec if lo <= c % 30 < lo + 2]
        pos = [w for w in v if w > 0]
        wv[str(lo)] = {"p": round(len(pos) / len(v), 3), "n_mean": round(st.mean(pos), 2) if pos else 0, "n": len(v)}
        md("| %d-%d | %.2f | %.1f | %d |" % (lo, lo + 2, wv[str(lo)]["p"], wv[str(lo)]["n_mean"], len(v)))
    P["wave"] = {"by_phase30": wv, "period": 30}

    # ---------------------------------------------------------------- progression
    lv = collections.defaultdict(list); buy = collections.defaultdict(list); sk = collections.defaultdict(list)
    for n in lab_runs:
        ev = read_run(n)
        sn = [e for e in ev if e["kind"] == "snap" and e["clock"] >= 297.4]
        for p, e in zip(sn, sn[1:]):
            if e["level"] != p["level"]:
                lv[e["level"]].append((e["clock"], e["lh"], e["nw"]))
        for e in ev:
            if e["kind"] == "buy" and e["clock"] >= 297:
                buy[e["item"]].append((e["clock"], e["cost"]))
            if e["kind"] == "skill" and e["clock"] >= 297:
                sk[(e["ability"], e["level"])].append(e["clock"])
    prog = {"level_up_at_lh": {}, "skills": {}, "kaya_buy_clock": None}
    md("\n## Progression during the run (lab_10x)\n")
    md("| event | clock mean (sd) | cumulative LH at the event mean (sd) | n |\n|---|---|---|---|")
    for L in sorted(lv):
        v = lv[L]
        prog["level_up_at_lh"][str(L)] = {"lh_mean": round(st.mean(x[1] for x in v), 2), "lh_sd": round(st.pstdev([x[1] for x in v]), 2),
                                          "clock_mean": round(st.mean(x[0] for x in v), 1), "n": len(v)}
        md("| level %d | %.0f (%.0f) | %.1f (%.1f) | %d |" % (L, st.mean(x[0] for x in v), st.pstdev([x[0] for x in v]), st.mean(x[1] for x in v), st.pstdev([x[1] for x in v]), len(v)))
    for k, v in sorted(sk.items()):
        prog["skills"][k[0] + "_%d" % k[1]] = round(st.mean(v), 1)
        md("| skill %s -> %d | %.0f (%.0f) | at the level-up above | %d |" % (k[0], k[1], st.mean(v), st.pstdev(v), len(v)))
    for k, v in buy.items():
        c = [x[0] for x in v]
        md("| buy %s (cost %d) | %.0f (%.0f), range %.0f-%.0f | gold >= cost in fountain | %d |" % (k, v[0][1], st.mean(c), st.pstdev(c), min(c), max(c), len(c)))
        if k == "item_kaya":
            prog["kaya_buy_clock"] = {"mean": round(st.mean(c), 1), "sd": round(st.pstdev(c), 1), "cost": v[0][1]}
    P["progression"] = prog

    # ---------------------------------------------------------------- the user's own drill runs
    rows = list(csv.DictReader(open(os.path.join(ROOT, "runs.csv"), encoding="utf-8")))
    by = collections.defaultdict(dict)
    for r in rows:
        by[r["session"]][int(r["minute"])] = r
    gains = []
    for s, m in by.items():
        if s.startswith("2026-09-29") and 5 in m and 10 in m and m[5]["net_worth"] and m[10]["net_worth"] and int(m[10]["lh"]) > 50:
            gains.append((s, int(m[10]["net_worth"]) - int(m[5]["net_worth"]), int(m[10]["lh"]) - int(m[5]["lh"]), int(m[10]["fountain_stops"]) - int(m[5]["fountain_stops"])))
    P["user_drill"] = [{"session": g[0], "gain": g[1], "lh": g[2], "fountain_stops": g[3]} for g in gains]
    md("\n## Your own 5:00-10:00 drill runs (runs.csv, sessions 2026-09-29)\n")
    md("| session | nw gained 5:00-10:00 | fountain stops |\n|---|---|---|")
    for g in gains:
        md("| %s | %d | %d |" % (g[0], g[1], g[3]))
    md("\nmean %.0f (n=%d); lab_10x bot mean: see validation." % (st.mean(g[1] for g in gains), len(gains)))
