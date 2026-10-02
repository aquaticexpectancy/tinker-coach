"""Step 4, joint search: coordinate descent over every knob at once, from several starts, with common random numbers,
then a re-score of the winners on fresh seeds. (search.py scans each family exhaustively; this finds interactions.)
    python sim/search2.py [--runs 300]
"""
import sys, os, json, itertools, statistics as st, argparse, time, random, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim as S
import search as SR
from concurrent.futures import ProcessPoolExecutor

CYCLES = None


def all_cycles():
    out = []
    for L in range(3, 8):
        for seq in itertools.product("ABCD", repeat=L):
            if any(seq[i] == seq[(i + 1) % L] for i in range(L)):
                continue
            if "B" not in seq or "A" not in seq or "D" not in seq or seq[0] != "A":
                continue
            out.append("".join(seq))
    return out


def knobs():
    k = {}
    for s in "ACDE":
        k["N4_" + s] = [1, 2, 3, 4]
        k["L4_" + s] = [True, False]
    for s in "ADE":
        k["N3_" + s] = [1, 2, 3, 4]
        k["L3_" + s] = [True, False]
    k["B_N"] = [None, 1, 2, 3]
    k["X"] = [None, 300, 360, 420, 480, 540, 600, 700, 800]
    k["chain"] = [None, -100, 0, 100, 200, 300, 500]
    k["order"] = [None] + all_cycles()
    return k


BASE = {"N4_A": 2, "N4_C": 3, "N4_D": 3, "N4_E": 2, "L4_A": True, "L4_C": True, "L4_D": True, "L4_E": True,
        "N3_A": 3, "N3_D": 3, "N3_E": 3, "L3_A": True, "L3_D": True, "L3_E": False,
        "B_N": None, "X": None, "chain": None, "order": None}


def to_cfg(v, name="x"):
    cfg = {"name": name, "N": {"4": {s: v["N4_" + s] for s in "ACDE"}, "3": {s: v["N3_" + s] for s in "ADE"}},
           "L": {"4": {s: v["L4_" + s] for s in "ACDE"}, "3": {s: v["L3_" + s] for s in "ADE"}}}
    if v["B_N"]:
        cfg["B_N"] = v["B_N"]
    if v["X"] is not None:
        cfg["X"] = v["X"]
    if v["chain"] is not None:
        cfg["chain"] = v["chain"]
    if v["order"]:
        cfg["order"] = list(v["order"])
    return cfg


def _eval(a):
    cfg, runs, seed0 = a
    r = SR.evaluate(cfg, runs, seed0)
    return r


def descend(pool, start, runs, ks, log, seed0=0, rounds=4):
    cur = dict(start)
    cur_r = SR.evaluate(to_cfg(cur), runs, seed0)
    for rd in range(rounds):
        changed = False
        order = list(ks)
        random.Random(rd).shuffle(order)
        for k in order:
            cands = [dict(cur, **{k: val}) for val in ks[k] if val != cur[k]]
            rs = list(pool.map(_eval, [(to_cfg(c), runs, seed0) for c in cands], chunksize=8))
            best_i = max(range(len(rs)), key=lambda i: rs[i]["gain"])
            d, se = SR.paired(rs[best_i], cur_r)
            if d > 1.5 * se and d > 3:
                cur, cur_r = cands[best_i], rs[best_i]
                changed = True
                log("  round %d: %-6s -> %-10s  %.0f (+%.0f)" % (rd, k, cur[k], cur_r["gain"], d))
        if not changed:
            break
    return cur, cur_r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=300)
    a = ap.parse_args()
    ks = knobs()
    lines = []

    def say(s=""):
        print(s, flush=True)
        lines.append(s)

    t0 = time.time()
    with ProcessPoolExecutor(max_workers=int(os.environ.get("SIM_WORKERS", max(1, (os.cpu_count() or 4) - 1))), initializer=SR._init) as pool:
        base = SR.evaluate(to_cfg(BASE, "bot"), a.runs * 2, 0)
        say("bot: %.0f" % base["gain"])
        starts = {"bot": dict(BASE),
                  "fewer Marches": dict(BASE, N4_C=2, N4_D=2),
                  "ABCBDB cycle": dict(BASE, order="ABCBDB"),
                  "random": {k: random.Random(11).choice(v) for k, v in ks.items()}}
        finals = []
        for name, s0 in starts.items():
            say("\nstart: %s" % name)
            v, r = descend(pool, s0, a.runs, ks, say)
            say("  -> %.0f" % r["gain"])
            finals.append((name, v))
        # fresh seeds
        say("\nre-scored on fresh seeds (1000+, %d games):" % (a.runs * 4))
        b = SR.evaluate(to_cfg(BASE, "bot"), a.runs * 4, 1000)
        out = []
        seen = set()
        for name, v in finals:
            key = json.dumps(v, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            r = SR.evaluate(to_cfg(v, "from " + name), a.runs * 4, 1000)
            d, se = SR.paired(r, b)
            say("%-22s %s  d vs bot %+.0f +/- %.0f" % ("from " + name, SR.fmt(r)[:80], d, 2 * se))
            out.append({"name": "from " + name, "cfg": to_cfg(v, "from " + name), "knobs": v, "gain": r["gain"], "d": d, "se": se,
                        "lh": r["lh"], "home": r["home"], "sd": r["sd"], "mana_out": r["mana_out"]})
        json.dump({"bot": {"gain": b["gain"], "sd": b["sd"], "lh": b["lh"], "home": b["home"]}, "finalists": out},
                  open(os.path.join(S.HERE, "search2_results.json"), "w"), indent=1)
        json.dump([o["cfg"] for o in out], open(os.path.join(S.HERE, "finalists.json"), "w"), indent=1)
    open(os.path.join(S.HERE, "SEARCH2.md"), "w", encoding="utf-8").write("```\n" + "\n".join(lines) + "\n```\n")
    print("done %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
