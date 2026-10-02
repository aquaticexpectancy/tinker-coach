"""Step 3: run the bot's own policy in the simulator and compare with the real lab_10x runs.

    python sim/validate.py [--runs 400]  ->  prints the table and writes sim/VALIDATION.md
"""
import sys, os, json, statistics as st, collections, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from load import *
from trips import trips_of
import sim as S


def real_metrics(setup="lab_10x", only=None):
    out = []
    for n in runs_of(setup):
        if only is not None and n not in only:
            continue
        ev = read_run(n)
        end = next((e for e in ev if e["kind"] == "end"), None)
        ds = next((e for e in ev if e["kind"] == "drill_start"), None)
        if not end or not ds:
            continue
        s0 = next(e for e in ev if e["kind"] == "snap" and e["clock"] > ds["clock"] + 0.2)
        ts = trips_of(ev)
        if not ts:
            continue
        gain = end["nw"] - s0["nw"]
        homes = [t["t_next_out"] - t["t_home"] for t in ts if t["t_home"] and t["t_next_out"]]
        stops = [t["t_next_out"] - t["t_landF"] for t in ts if t["t_landF"] and t["t_next_out"]]
        sn = [e for e in ev if e["kind"] == "snap" and e["clock"] >= 297.4]
        cum = {}
        for m in (6, 7, 8, 9, 10):
            s = max((e for e in sn if e["clock"] <= m * 60), key=lambda e: e["clock"])
            cum[m] = s["nw"] - s0["nw"]
        st_lh = collections.defaultdict(list)
        for t in ts:
            if t["lh"] is not None:
                st_lh[t["station"]].append(t["lh"])
        out.append({"gain": gain, "lh": end["lh"], "trips": len(ts), "camp_trips": sum(t["station"] != "B" for t in ts),
                    "wave_trips": sum(t["station"] == "B" for t in ts), "home_secs": sum(homes), "stop": st.mean(stops),
                    "mana_home": st.mean(t["mana_home"] for t in ts if t["mana_home"] is not None),
                    "mana_out": st.mean(t["mana_out"] for t in ts), "mana_home_all": [t["mana_home"] for t in ts if t["mana_home"] is not None],
                    "mana_out_all": [t["mana_out"] for t in ts], "level": end["level"], "cum": cum,
                    "visits": {s: sum(t["station"] == s for t in ts) for s in "ABCDE"},
                    "lh_per_trip": {s: st.mean(v) for s, v in st_lh.items()}, "level_end": end["level"]})
    return out


def sim_metrics(P, policy, runs, seed0=1000):
    out = []
    for i in range(runs):
        r = S.run(P, policy, seed=seed0 + i)
        sim = r["sim"]
        cum = {}
        for m in (6, 7, 8, 9, 10):
            g = sum(x for tt, x in [(a, b) for a, b in sim.timeline[:0]])      # placeholder
            cum[m] = None
        # cumulative gain by minute from the credit timeline (bounty) + passive
        tl = sim.timeline
        for m in (6, 7, 8, 9, 10):
            bounty = 0.0
            for tt, g in tl:
                if tt <= m * 60:
                    bounty = g
            cum[m] = bounty + P["passive_gold_per_s"] * (m * 60 - 297.5)
        vis = collections.Counter(t["S"] for t in sim.trips)
        stl = collections.defaultdict(list)
        for t in sim.trips:
            stl[t["S"]].append(t["lh"])
        out.append({"gain": r["gain"], "lh": r["lh"], "trips": r["trips"], "camp_trips": r["camp_trips"], "wave_trips": r["wave_trips"],
                    "home_secs": r["home_secs"], "stop": st.mean(r["stops"][1:]) if len(r["stops"]) > 1 else 0,
                    "mana_home": st.mean(r["log_home"]), "mana_out": st.mean(r["log_out"]), "mana_home_all": r["log_home"],
                    "mana_out_all": r["log_out"], "level": r["level"], "cum": cum, "visits": {s: vis.get(s, 0) for s in "ABCDE"},
                    "lh_per_trip": {s: st.mean(v) for s, v in stl.items() if v}})
    return out


def ms(v):
    return st.mean(v), st.pstdev(v)


def table(real, simr, extra=()):
    rows = []
    items = [("gold gained 5:00-10:00 (nw)", "gain"), ("last hits", "lh"), ("trips", "trips"), ("camp trips", "camp_trips"), ("wave (B) trips", "wave_trips"),
             ("seconds going home (sum)", "home_secs"), ("fountain stop (s, landing->Keen out)", "stop"),
             ("mana at Keen home order (mean per run)", "mana_home"), ("mana at Keen out order (mean per run)", "mana_out")]
    for label, k in items:
        a, sa = ms([r[k] for r in real])
        b, sb = ms([r[k] for r in simr])
        z = (b - a) / sa if sa else 0
        rows.append((label, a, sa, b, sb, z))
    for m in (6, 7, 8, 9, 10):
        a, sa = ms([r["cum"][m] for r in real])
        b, sb = ms([r["cum"][m] for r in simr])
        rows.append(("gold gained by %d:00" % m, a, sa, b, sb, (b - a) / sa))
    for s in "ABCDE":
        a, sa = ms([r["visits"][s] for r in real])
        b, sb = ms([r["visits"][s] for r in simr])
        rows.append(("trips to %s" % s, a, sa, b, sb, (b - a) / sa if sa else 0))
    for s in "ABCDE":
        a, sa = ms([r["lh_per_trip"][s] for r in real if s in r["lh_per_trip"]])
        b, sb = ms([r["lh_per_trip"][s] for r in simr if s in r["lh_per_trip"]])
        rows.append(("LH per trip at %s" % s, a, sa, b, sb, (b - a) / sa if sa else 0))
    return rows


def quant(v, qs=(10, 25, 50, 75, 90)):
    v = sorted(v)
    return [v[int(len(v) * q / 100)] for q in qs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=300)
    ap.add_argument("--out", default=os.path.join(S.HERE, "VALIDATION.md"))
    ap.add_argument("--holdout", action="store_true", help="payoffs from the other half of the lab_10x games, compare on this half")
    a = ap.parse_args()
    P = S.load_params()
    only = None
    if a.holdout:
        names = sorted(runs_of("lab_10x"))
        test = set(names[1::2])
        P["payoff_records"] = [r for r in P["payoff_records"] if not (r["setup"] == "lab_10x" and r["run"] in test)]
        only = test
    real = real_metrics(only=only)
    simr = sim_metrics(P, S.BotPolicy(), a.runs)
    rows = table(real, simr)
    md = ["# Validation: the bot's lab_10x policy in the simulator vs the real runs\n",
          "real = %d lab_10x games (mean, run-to-run sd); sim = %d simulated games. z = (sim mean - real mean) / real sd; |z| < 1 means the simulator mean is inside the real spread.\n" % (len(real), len(simr)),
          "| metric | real mean | real sd | sim mean | sim sd | z |\n|---|---|---|---|---|---|"]
    bad = 0
    for label, am, asd, bm, bsd, z in rows:
        flag = "" if abs(z) < 1 else " **"
        bad += abs(z) >= 1
        md.append("| %s | %.1f | %.1f | %.1f | %.1f | %+.2f%s |" % (label, am, asd, bm, bsd, z, flag))
    md.append("\nMana at each Keen-home order (all orders pooled), quantiles 10/25/50/75/90:")
    rh = [x for r in real for x in r["mana_home_all"]]
    sh = [x for r in simr for x in r["mana_home_all"]]
    md.append("- real: %s (n=%d, mean %.0f)" % ([round(x) for x in quant(rh)], len(rh), st.mean(rh)))
    md.append("- sim:  %s (n=%d, mean %.0f)" % ([round(x) for x in quant(sh)], len(sh), st.mean(sh)))
    ro = [x for r in real for x in r["mana_out_all"]]
    so = [x for r in simr for x in r["mana_out_all"]]
    md.append("\nMana at each Keen-out order (leaving the fountain), quantiles 10/25/50/75/90:")
    md.append("- real: %s (mean %.0f)" % ([round(x) for x in quant(ro)], st.mean(ro)))
    md.append("- sim:  %s (mean %.0f)" % ([round(x) for x in quant(so)], st.mean(so)))
    md.append("\nrows outside |z|<1: %d of %d" % (bad, len(rows)))
    txt = "\n".join(md)
    open(a.out, "w", encoding="utf-8").write(txt + "\n")
    print(txt)


if __name__ == "__main__":
    main()
