"""Final report on Immortal March use from data/nhp_camptrips.json (+ laser targets from the raw HP lines)."""
import collections, csv, json, statistics as st, bisect
T = [t for t in json.load(open("data/nhp_camptrips.json")) if t["st"] in "ACDE" and t["camps"]]
med = lambda v: round(st.median(v)) if v else None
H = lambda t, k: sum(c["hp"][str(k)] if str(k) in c["hp"] else c["hp"][k] for c in t["camps"].values())
H0 = lambda t: sum(c["hp0"] for c in t["camps"].values())
out = {"games": len({t["g"] for t in T}), "trips": len(T), "stations": {}, "thresholds": {}}
for stn in "ACDE":
    for lab, lo, hi in (("m3", 1, 6), ("m4", 7, 30)):
        X = [t for t in T if t["st"] == stn and lo <= t["lvl"] <= hi]
        if len(X) < 8: continue
        dmg = [(H0(t) - sum(c["end"] for c in t["camps"].values())) / t["n_m"] for t in X if t["n_m"]]
        out["stations"][f"{stn}_{lab}"] = {
            "trips": len(X), "camp_hp": med([H0(t) for t in X]), "creeps": med([sum(c["n"] for c in t["camps"].values()) for t in X]),
            "marches": round(st.mean([t["n_m"] for t in X]), 2), "lasers": round(st.mean([t["n_l"] for t in X]), 2),
            "on_site_s": med([t["on_site"] for t in X]), "hp_removed_per_march": med(dmg),
            "left_after_robots_pct": med([100 * sum(c["end"] for c in t["camps"].values()) / max(1, H0(t)) for t in X]),
            "creeps_left": med([sum(c["alive"] for c in t["camps"].values()) for t in X]),
            "march_counts": dict(collections.Counter(t["n_m"] for t in X))}
    # threshold for March 3 (and 4): HP left 6 s after the 1st March, best split between "stopped at N" and "went on"
    for n in (2, 3):
        X = [t for t in T if t["st"] == stn and t["lvl"] >= 7 and t["n_m"] >= n]
        if len(X) < 12: continue
        pts = [(H(t, 6 if n == 2 else 9), t["n_m"] > n) for t in X]
        best = max(((sum((hp >= th) == more for hp, more in pts) / len(pts), th) for th in range(1000, 9000, 100)))
        out["thresholds"][f"{stn}_after_{n}"] = {"hp_left": best[1], "agreement": round(best[0], 2), "n": len(X),
                                                 "went_on_share": round(sum(m for _, m in pts) / len(pts), 2)}
json.dump(out, open("data/nhp_report.json", "w"), indent=1)
print(json.dumps(out, indent=1))
