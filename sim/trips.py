"""Turn a bot run (bot_runs/*.jsonl) into one record per trip: keen out of the fountain, the camp work, keen home,
the fountain stop. Used by measure.py (parameters) and validate.py (real-run metrics)."""
import bisect
from load import read_run

START_CLOCK = 297.0            # drill_start


def run_series(ev):
    snaps = [e for e in ev if e["kind"] == "snap" and e["clock"] >= 297.4]
    return snaps


def snap_at(snaps, sc, t, side="before"):
    """The snapshot at or just before t (side before) / at or just after (side after)."""
    if side == "before":
        i = bisect.bisect_right(sc, t) - 1
    else:
        i = bisect.bisect_left(sc, t)
    i = max(0, min(len(snaps) - 1, i))
    return snaps[i]


def trips_of(name_or_ev):
    ev = read_run(name_or_ev) if isinstance(name_or_ev, str) else name_or_ev
    snaps = run_series(ev)
    sc = [s["clock"] for s in snaps]
    keens = [e for e in ev if e["kind"] == "keen"]
    landed = [e for e in ev if e["kind"] == "landed"]
    casts = [e for e in ev if e["kind"] == "cast"]
    tripev = [e for e in ev if e["kind"] == "trip"]
    tc = [e for e in ev if e["kind"] == "trip_creeps"]
    dec = [e for e in ev if e["kind"] == "decision" and e.get("what") == "station"]
    skills = [e for e in ev if e["kind"] == "skill"]
    end = next((e for e in ev if e["kind"] == "end"), None)
    out = []
    outs = [k for k in keens if k["to"] != "F"]            # keen out of the fountain, one per trip
    for i, k in enumerate(outs):
        st = k["to"]
        t_out = k["clock"]
        # the matching home keen: first keen to F after this one
        home = next((h for h in keens if h["to"] == "F" and h["clock"] > t_out), None)
        t_next_out = outs[i + 1]["clock"] if i + 1 < len(outs) else (end["clock"] if end else None)
        land = next((l for l in landed if l["station"] == st and l["clock"] >= t_out), None)
        landF = next((l for l in landed if l["station"] == "F" and home and l["clock"] >= home["clock"]), None)
        if not land:
            continue
        t_land = land["clock"]
        t_home = home["clock"] if home else None
        work = [c for c in casts if t_land <= c["clock"] <= (t_home or 1e9)]
        marches = [c for c in work if c["ability"] == "march"]
        rearms = [c for c in work if c["ability"] == "rearm"]
        lasers = [c for c in work if c["ability"] == "laser"]
        te = next((t for t in tripev if t["station"] == st and t["clock"] >= (landF["clock"] if landF else t_land)), None)
        # creeps seen at arrival / at the last look of the trip
        mine = [c for c in tc if c["station"] == st and c.get("start") is not None and abs(c["start"] - t_land) < 0.3]
        first = min(mine, key=lambda c: c["dt"]) if mine else None
        last = max(mine, key=lambda c: c["dt"]) if mine else None
        s_out = snap_at(snaps, sc, t_out)
        s_land = snap_at(snaps, sc, t_land, "after")
        s_home = snap_at(snaps, sc, t_home) if t_home else None
        s_next = snap_at(snaps, sc, t_next_out) if t_next_out else None
        lvl = s_land["level"]
        ml = max([s["level"] for s in skills if s["ability"] == "tinker_march_of_the_machines" and START_CLOCK <= s["clock"] <= t_land] or [3])
        ll = max([s["level"] for s in skills if s["ability"] == "tinker_laser" and START_CLOCK <= s["clock"] <= t_land] or [2])
        out.append({
            "station": st, "t_out": t_out, "mana_out": k["mana"], "t_land": t_land, "mana_land": land["mana"],
            "off_target": land.get("off_target"),
            "t_first_march": marches[0]["clock"] if marches else None,
            "march_times": [c["clock"] for c in marches], "rearm_times": [c["clock"] for c in rearms],
            "laser_times": [c["clock"] for c in lasers],
            "n_march": len(marches), "n_laser": len(lasers), "n_rearm_trip": len(rearms),
            "t_home": t_home, "mana_home": home["mana"] if home else None,
            "t_landF": landF["clock"] if landF else None, "mana_landF": landF["mana"] if landF else None,
            "t_next_out": t_next_out,
            "lh": te["last_hits"] if te else None, "creeps_left": te["creeps_left"] if te else None,
            "seconds": te["seconds"] if te else None,
            "gold_land": s_land["gold"], "gold_home": s_home["gold"] if s_home else None,
            "gold_next": s_next["gold"] if s_next else None,
            "nw_land": s_land["nw"], "nw_next": s_next["nw"] if s_next else None,
            "lh_land": s_land["lh"], "lh_next": s_next["lh"] if s_next else None,
            "level": lvl, "march_level": ml, "laser_level": ll, "max_mana": s_land["max_mana"],
            "n_arrive": len(first["creeps"]) if first else None,
            "hp_arrive": sum(c[2] for c in first["creeps"]) if first else None,
            "n_end": len(last["creeps"]) if last else None,
            "wave": next((d.get("wave") for d in dec if abs(d["clock"] - (t_out)) < 1.5), None),
        })
    return out


if __name__ == "__main__":
    import sys, json
    for t in trips_of(sys.argv[1])[:6]:
        print(json.dumps(t))
