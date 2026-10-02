"""How much do the search results depend on the least certain parameters?
Re-scores the bot and the finalists with one parameter perturbed at a time.
    python sim/sensitivity.py [--runs 600] [--cfgs search_results.json]
"""
import sys, os, json, copy, statistics as st, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim as S
import search as SR
from concurrent.futures import ProcessPoolExecutor

_BASEP = None


def _init():
    global _BASEP
    _BASEP = S.load_params()


def perturb(P, name):
    P = copy.deepcopy(P)
    c = P["camps"]
    if name == "leak x0.5":
        c["leak_per_minute_by_station"] = {k: v * 0.5 for k, v in c["leak_per_minute_by_station"].items()}
        c["leak_per_minute"] *= 0.5
    elif name == "leak x1.5":
        c["leak_per_minute_by_station"] = {k: min(1, v * 1.5) for k, v in c["leak_per_minute_by_station"].items()}
        c["leak_per_minute"] *= 1.5
    elif name == "laser ok -0.2":
        for k in P["laser_ok"]:
            P["laser_ok"][k]["p"] = max(0, P["laser_ok"][k]["p"] - 0.2)
    elif name == "laser ok +0.2":
        for k in P["laser_ok"]:
            P["laser_ok"][k]["p"] = min(1, P["laser_ok"][k]["p"] + 0.2)
    elif name == "wave seen 0.5":
        P["wave_visible_p"] = 0.5
    elif name == "wave seen 0.9":
        P["wave_visible_p"] = 0.9
    elif name == "off-plan payoff -20%":
        P["_off_delta"] = -0.2
    elif name == "off-plan payoff -10%":
        P["_off_delta"] = -0.1
    elif name == "off-plan payoff +10%":
        P["_off_delta"] = 0.1
    elif name == "gold per kill -8%":
        P["_gold_scale"] = 0.92
    elif name == "gold per kill +8%":
        P["_gold_scale"] = 1.08
    elif name == "bot books 20% more leftovers away":
        P["camps"]["booked_vs_real_same_minute"]["booked_mean"] *= 0.8
    elif name == "bootstrap payoffs (half the records)":
        import random
        rng = random.Random(7)
        P["payoff_records"] = [r for r in P["payoff_records"] if rng.random() < 0.5 or r["setup"] != "lab_10x"]
    return P


def _eval(args):
    cfg, pname, runs = args
    P = perturb(_BASEP, pname)
    S.Payoffs  # noqa
    pol = SR.ParamPolicy(cfg)
    g = [S.run(P, pol, seed=500 + i)["gain"] for i in range(runs)]
    return cfg.get("name"), pname, g


PERTS = ["none", "leak x0.5", "leak x1.5", "laser ok -0.2", "laser ok +0.2", "wave seen 0.5", "wave seen 0.9",
         "off-plan payoff -20%", "off-plan payoff -10%", "off-plan payoff +10%", "gold per kill -8%", "gold per kill +8%",
         "bot books 20% more leftovers away", "bootstrap payoffs (half the records)"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=600)
    ap.add_argument("--cfgs", default=os.path.join(S.HERE, "finalists.json"))
    a = ap.parse_args()
    cfgs = [{"name": "bot"}] + json.load(open(a.cfgs))
    jobs = [(c, p, a.runs) for p in PERTS for c in cfgs]
    with ProcessPoolExecutor(max_workers=int(os.environ.get("SIM_WORKERS", max(1, (os.cpu_count() or 4) - 1))), initializer=_init) as pool:
        res = list(pool.map(_eval, jobs, chunksize=2))
    tab = {}
    for name, p, g in res:
        tab[(name, p)] = g
    names = [c["name"] for c in cfgs]
    lines = ["| perturbation | " + " | ".join(n for n in names) + " |", "|---|" + "---|" * len(names)]
    out = {}
    for p in PERTS:
        row = []
        for n in names:
            g = tab[(n, p)]
            b = tab[("bot", p)]
            d = [x - y for x, y in zip(g, b)]
            row.append("%.0f (%+.0f)" % (st.mean(g), st.mean(d)) if n != "bot" else "%.0f" % st.mean(g))
            out.setdefault(p, {})[n] = {"gain": st.mean(g), "d": st.mean(d), "se": st.pstdev(d) / len(d) ** 0.5}
        lines.append("| %s | %s |" % (p, " | ".join(row)))
    txt = "\n".join(lines)
    print(txt)
    open(os.path.join(S.HERE, "SENSITIVITY.md"), "w", encoding="utf-8").write(
        "Mean gold gained 5:00-10:00 (difference to the bot in brackets), one parameter changed at a time, same seeds.\n\n" + txt + "\n")
    json.dump(out, open(os.path.join(S.HERE, "sensitivity.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
