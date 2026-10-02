"""Step 4: search for a better policy in the simulator.

A policy = Marches per station (+Laser), fountain-wait threshold, chaining rule, station routing. The simulator is fast
(~2 ms a game), so the structured spaces are searched exhaustively with common random numbers:
  stage 1  one-dimensional sweeps from the bot (fountain threshold, chaining margin, Marches per station, Laser)
  stage 2  every March-count vector (ml4: 4^4 = 256, ml3: 4^3 = 64) x Laser on/off
  stage 3  grid of fountain threshold x chaining margin x routing on the best counts
  stage 4  re-score the winners on fresh seeds (selection on one seed set, report on another)
    python sim/search.py [--runs 400]
"""
import sys, os, json, itertools, statistics as st, argparse, time, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim as S
from concurrent.futures import ProcessPoolExecutor

_P = None


def _init():
    global _P
    _P = S.load_params()


class ParamPolicy(S.BotPolicy):
    """The bot's policy with the new knobs; with default knobs it is the bot."""

    def __init__(self, cfg):
        super().__init__(p_away=cfg.get("p_away"), threat_p=cfg.get("threat_p", 0.0))
        self.cfg = cfg
        self.name = cfg.get("name", "param")
        self.cycle_i = 0

    def reset(self, sim):
        super().reset(sim)
        self.cycle_i = 0

    # ---- Marches per station
    def plan(self, sim, S_):
        c = self.cfg
        if S_ == "B":
            if c.get("B_N"):
                return {"N": c["B_N"], "laser": c.get("B_laser", True)}
            return super().plan(sim, S_)
        ml = sim.march_lvl()
        base_n, base_l = S.LAB_PLAN[ml].get(S_, S.LAB_PLAN[4].get(S_, (3, True)))
        n = c.get("N", {}).get(str(ml), {}).get(S_, base_n)
        l = c.get("L", {}).get(str(ml), {}).get(S_, base_l)
        return {"N": n, "laser": l}

    # ---- fountain wait
    def leave_ok(self, sim, pick, dwell):
        X = self.cfg.get("X")
        if X is None:
            return super().leave_ok(sim, pick, dwell)
        kc = sim.price("keen")
        if dwell >= self.cfg.get("X_cap", 15):
            return True
        return dwell >= 3.5 and (sim.mana >= X or sim.mana >= sim.maxm() * 0.97)

    # ---- routing
    def decide(self, sim, in_f, here):
        order = self.cfg.get("order")
        if not order:
            return super().decide(sim, in_f, here)
        self.minute_update(sim)
        wave = sim.wave_at(sim.t)
        sim.wave_seen = wave
        n = len(order)
        for k in range(n):
            s = order[(self.cycle_i + k) % n]
            if s == "B" and not wave:
                continue
            if s == "C" and sim.march_lvl() < 4:
                continue
            if s == self.last and n > 1:
                continue
            self.cycle_i = (self.cycle_i + k + 1) % n
            return s
        return "F"

    # ---- chaining
    def trip_need(self, sim, s):
        mc, rc, kc = sim.price("march"), sim.price("rearm"), sim.price("keen")
        pl = self.plan(sim, s) if s != "B" else {"N": 2}
        n = pl["N"]
        return n * mc + (n - 1) * rc + kc + 40

    def after_trip(self, sim, trip):
        c = self.cfg
        if c.get("chain") is None:
            return super().after_trip(sim, trip)
        rc, kc = sim.price("rearm"), sim.price("keen")
        wave = sim.wave_at(sim.t)
        if c.get("order"):
            saved = self.cycle_i
            pick = self.decide(sim, False, trip["S"])
            self.cycle_i = saved
        else:
            pick = self.rate_route(sim, sim.t, wave, trip["S"], False)
        if pick == "F":
            return "F"
        sim.wave_seen = wave
        extra = 0 if (sim.t >= sim.march_ready and sim.t >= sim.keen_ready) else rc
        need = extra + kc + self.trip_need(sim, pick) - sim.charges * 60 + c["chain"]
        if sim.mana < need:
            return "F"
        if c.get("order"):
            self.cycle_i = (self.cycle_i + 1) % len(c["order"])
        return pick


def evaluate(cfg, runs=400, seed0=0):
    P = _P or S.load_params()
    pol = ParamPolicy(cfg)
    g = []
    lh = []
    home = []
    mo = []
    ct = []
    for i in range(runs):
        r = S.run(P, pol, seed=seed0 + i)
        g.append(r["gain"])
        lh.append(r["lh"])
        home.append(r["home_secs"])
        mo.append(sum(r["log_out"]) / max(1, len(r["log_out"])))
        ct.append(r["trips"])
    return {"cfg": cfg, "gain": st.mean(g), "sd": st.pstdev(g), "lh": st.mean(lh), "home": st.mean(home), "mana_out": st.mean(mo),
            "trips": st.mean(ct), "gains": g}


def _eval(args):
    return evaluate(*args)


def run_many(pool, cfgs, runs, seed0=0):
    return list(pool.map(_eval, [(c, runs, seed0) for c in cfgs], chunksize=4))


def paired(a, b):
    d = [x - y for x, y in zip(a["gains"], b["gains"])]
    m = st.mean(d)
    se = st.pstdev(d) / len(d) ** 0.5
    return m, se


def fmt(r, base=None):
    s = "%7.0f  sd %4.0f  LH %5.1f  trips %4.1f  home %5.1f s  mana-out %4.0f" % (r["gain"], r["sd"], r["lh"], r["trips"], r["home"], r["mana_out"])
    if base is not None:
        m, se = paired(r, base)
        s += "  d vs bot %+6.0f +/- %3.0f" % (m, 2 * se)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=400)
    ap.add_argument("--out", default=os.path.join(S.HERE, "search_results.json"))
    a = ap.parse_args()
    runs = a.runs
    t0 = time.time()
    out = {"stages": {}}
    log = []

    def say(s=""):
        print(s, flush=True)
        log.append(s)

    with ProcessPoolExecutor(max_workers=int(os.environ.get("SIM_WORKERS", max(1, (os.cpu_count() or 4) - 1))), initializer=_init) as pool:
        base = run_many(pool, [{"name": "bot"}], runs)[0]
        say("BASELINE (the bot, lab plan, fountain after every trip): " + fmt(base))
        # ---------------- stage 1
        say("\n== stage 1: one-dimensional sweeps from the bot ==")
        cfgs = [{"name": "X=%d" % X, "X": X} for X in range(300, 861, 60)]
        cfgs += [{"name": "chain+%d" % m, "chain": m} for m in (-100, 0, 100, 200, 300, 400, 600)]
        res = run_many(pool, cfgs, runs)
        out["stages"]["1_sweeps"] = [{"cfg": r["cfg"], "gain": r["gain"], "sd": r["sd"], "lh": r["lh"], "home": r["home"]} for r in res]
        for r in res:
            say("%-10s %s" % (r["cfg"]["name"], fmt(r, base)))
        # ---------------- stage 2: March counts
        say("\n== stage 2: every March-count vector ==")
        c4 = []
        for ns in itertools.product((1, 2, 3, 4), repeat=4):
            for ls in itertools.product((True, False), repeat=2):          # Laser at A,D (the stations that fire it often)
                c4.append({"name": "ml4 N=%s L(A,D)=%s" % (ns, ls),
                           "N": {"4": dict(zip("ACDE", ns))}, "L": {"4": {"A": ls[0], "D": ls[1]}}})
        res4 = run_many(pool, c4, runs)
        res4.sort(key=lambda r: -r["gain"])
        say("ml4 (March 4, 7:00 on): best 8 of %d" % len(res4))
        for r in res4[:8]:
            say("%-34s %s" % (r["cfg"]["name"], fmt(r, base)))
        c3 = []
        for ns in itertools.product((1, 2, 3, 4), repeat=3):
            c3.append({"name": "ml3 N(A,D,E)=%s" % (ns,), "N": {"3": dict(zip("ADE", ns))}})
        res3 = run_many(pool, c3, runs)
        res3.sort(key=lambda r: -r["gain"])
        say("ml3 (March 3, until ~6:12): best 5 of %d" % len(res3))
        for r in res3[:5]:
            say("%-34s %s" % (r["cfg"]["name"], fmt(r, base)))
        best_n = {"4": res4[0]["cfg"]["N"]["4"], "3": res3[0]["cfg"]["N"]["3"]}
        best_l = res4[0]["cfg"]["L"]
        out["stages"]["2_counts"] = {"ml4_top": [{"name": r["cfg"]["name"], "gain": r["gain"]} for r in res4[:20]],
                                     "ml3_top": [{"name": r["cfg"]["name"], "gain": r["gain"]} for r in res3[:10]]}
        # ---------------- stage 3: fountain x chaining x routing on the best counts
        say("\n== stage 3: fountain threshold x chaining x routing on the best counts ==")
        cycles = []
        for L in range(3, 8):
            for seq in itertools.product("ABCD", repeat=L):
                if any(seq[i] == seq[(i + 1) % L] for i in range(L)):
                    continue
                if "B" not in seq or "A" not in seq or "D" not in seq:
                    continue
                if seq[0] != "A":
                    continue
                cycles.append("".join(seq))
        base_cfg = {"N": best_n, "L": best_l}
        g3 = []
        for X in (None, 400, 500, 600, 700, 800):
            for ch in (None, 0, 150, 300):
                g3.append(dict(base_cfg, X=X, chain=ch, name="X=%s chain=%s" % (X, ch)) if X is not None else dict(base_cfg, chain=ch, name="X=bot chain=%s" % ch))
        res = run_many(pool, g3, runs)
        res.sort(key=lambda r: -r["gain"])
        for r in res[:10]:
            say("%-26s %s" % (r["cfg"]["name"], fmt(r, base)))
        top3 = res[0]
        out["stages"]["3_grid"] = [{"name": r["cfg"]["name"], "gain": r["gain"], "home": r["home"]} for r in res[:20]]
        say("\nfixed station cycles (%d sequences of length 3-7 over A,B,C,D, B taken only when a wave is up) with the best knobs:" % len(cycles))
        base2 = {k: v for k, v in top3["cfg"].items() if k != "name"}
        resc = run_many(pool, [dict(base2, order=list(c), name="cycle " + c) for c in cycles], max(100, runs // 3))
        resc.sort(key=lambda r: -r["gain"])
        for r in resc[:8]:
            say("%-26s %s" % (r["cfg"]["name"], fmt(r, base)))
        out["stages"]["3_cycles"] = [{"name": r["cfg"]["name"], "gain": r["gain"]} for r in resc[:20]]
        # ---------------- stage 4: fresh seeds
        say("\n== stage 4: winners re-scored on fresh seeds (1000+) ==")
        finalists = [dict(base_cfg, name="best counts only"), {k: v for k, v in top3["cfg"].items()}, dict(resc[0]["cfg"])] + \
                    [dict(r["cfg"]) for r in res[1:4]]
        fin = run_many(pool, [{"name": "bot"}] + finalists, runs * 2, seed0=1000)
        b0 = fin[0]
        out["final"] = []
        for r in fin:
            say("%-30s %s" % (r["cfg"]["name"], fmt(r, b0)))
            out["final"].append({"cfg": r["cfg"], "gain": r["gain"], "sd": r["sd"], "lh": r["lh"], "home": r["home"],
                                 "d_vs_bot": paired(r, b0)[0], "se": paired(r, b0)[1]})
    out["baseline"] = {"gain": base["gain"], "sd": base["sd"], "lh": base["lh"], "home": base["home"]}
    json.dump(out, open(a.out, "w"), indent=1, default=str)
    open(os.path.join(S.HERE, "SEARCH.md"), "w", encoding="utf-8").write("```\n" + "\n".join(log) + "\n```\n")
    print("done in %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
