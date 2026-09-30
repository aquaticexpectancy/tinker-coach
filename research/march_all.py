import csv, json, math, os, statistics as st
D = "data"; camps = json.load(open(D + "/transition.json"))["camps"]
def rows(g, k): return list(csv.DictReader(open(f"{D}/{g}_{k}.csv")))
def wrap(a): return (a + 180) % 360 - 180
def load(g):
    snap, ev = rows(g, "snap"), rows(g, "events")
    start = float(snap[-1]["start"]); off = st.median(float(r["ts"]) - int(r["tick"]) / 30 for r in ev)
    clk = lambda t: int(t) / 30 + off - start
    team = int([h for h in rows(g, "heroes") if "Tinker" in h["cls"]][0]["team"])
    bl = [clk(r["tick"]) for r in ev if r["inflictor"] == "item_blink" and "tinker" in r["attacker"]]
    nw10 = next((int(s["nw"]) for s in snap if clk(s["tick"]) >= 600), None)
    ud = rows(g, "unitdeaths")
    neu = [(clk(r["tick"]), float(r["x"]), float(r["y"])) for r in ud if "Neutral" in r["cls"]]
    lane = [(clk(r["tick"]), float(r["x"]), float(r["y"])) for r in ud if "Lane" in r["cls"]]
    up = 45 if team == 2 else -135
    ms = []
    for r in csv.DictReader(open(f"{D}/march/{g}.csv")):
        t, x, y, yaw = clk(r["tick"]), float(r["x"]), float(r["y"]), float(r["yaw"])
        if not (300 <= t <= 1200): continue
        dn = [(a, b) for (tt, a, b) in neu if 0 <= tt - t <= 8 and math.hypot(a - x, b - y) < 1900]
        dl = [(a, b) for (tt, a, b) in lane if 0 <= tt - t <= 8 and math.hypot(a - x, b - y) < 1900]
        m = dict(t=t, x=x, y=y, yaw=yaw, nk=len(dn), lk=len(dl), pre=t < (bl[0] if bl else 9e9))
        if dn and len(dn) >= len(dl):
            cx, cy = sum(a for a, b in dn) / len(dn), sum(b for a, b in dn) / len(dn)
            c = min(camps, key=lambda c: math.hypot(c["x"] - cx, c["y"] - cy))
            m.update(kind="camp", dcamp=math.hypot(c["x"] - x, c["y"] - y), aim=abs(wrap(yaw - math.degrees(math.atan2(c["y"] - y, c["x"] - x)))))
        elif dl and abs(x - y) < 1600: m.update(kind="wave", up=abs(wrap(yaw - up)))
        else: m["kind"] = "other"
        ms.append(m)
    for a, b in zip(ms, ms[1:]):
        if b["kind"] == a["kind"] and b["t"] - a["t"] <= 14 and math.hypot(b["x"] - a["x"], b["y"] - a["y"]) < 900:
            b["turn"] = abs(wrap(b["yaw"] - a["yaw"])); b["nth"] = a.get("nth", 1) + 1
        else: b["nth"] = 1
    if ms: ms[0]["nth"] = 1
    return dict(ms=ms, nw10=nw10, blink=bl[0] if bl else None)
G = {g: load(g) for g in ["me", "pro"] + sorted(f[:-4] for f in os.listdir(D + "/march") if f[0] in "ps")}
json.dump(G, open(D + "/march_all.json", "w"))
a = lambda v: f"{st.mean(v):.2f} ({len(v):3d})" if v else "   -      "
groups = [("NEW 20 (Stratz, 09-28/29)", [g for g in G if g[0] == "s"]), ("old 23 Immortal + pro", [g for g in G if g[0] == "p"] + ["pro"]), ("you", ["me"])]
print("kills (count). 5:00-10:00, before Blink only\n")
print(f"{'':28s} | {'camp 2nd: same':14s} {'camp 2nd: 180':14s} | {'1st faces camp':14s} {'side':14s} {'back':14s} | {'<400 from camp':14s} {'400-700':14s} {'700+':14s}")
for lab, gs in groups:
    C = [m for g in gs for m in G[g]["ms"] if m["kind"] == "camp" and m["t"] < 600 and m["pre"]]
    f = [m for m in C if m["nth"] == 1]; s = [m for m in C if m["nth"] == 2 and "turn" in m]; far = [m for m in f if m["dcamp"] >= 400]
    print(f"{lab:28s} | {a([m['nk'] for m in s if m['turn'] < 60]):14s} {a([m['nk'] for m in s if m['turn'] >= 120]):14s} | "
          f"{a([m['nk'] for m in far if m['aim'] < 45]):14s} {a([m['nk'] for m in far if 45 <= m['aim'] < 135]):14s} {a([m['nk'] for m in far if m['aim'] >= 135]):14s} | "
          f"{a([m['nk'] for m in f if m['dcamp'] < 400]):14s} {a([m['nk'] for m in f if 400 <= m['dcamp'] < 700]):14s} {a([m['nk'] for m in f if m['dcamp'] >= 700]):14s}")
print("\nMID WAVES 5:00-20:00: 1st March angle to the lane, lane kills\n")
print(f"{'':28s} | {'0-30 (up lane)':14s} {'30-60':14s} {'60-120':14s} {'120+':14s} | {'2nd: <25 turn':14s} {'25-70':14s} {'70+':14s}")
for lab, gs in groups:
    W = [m for g in gs for m in G[g]["ms"] if m["kind"] == "wave"]
    f = [m for m in W if m["nth"] == 1]; s = [m for m in W if m["nth"] == 2 and "turn" in m]
    print(f"{lab:28s} | " + " ".join(f"{a([m['lk'] for m in f if lo <= m['up'] < hi]):14s}" for lo, hi in [(0, 30), (30, 60), (60, 120), (120, 181)]) + " | "
          + " ".join(f"{a([m['lk'] for m in s if lo <= m['turn'] < hi]):14s}" for lo, hi in [(0, 25), (25, 70), (70, 181)]))
print("\nnew-20 Blink first use:", sorted(f"{int(G[g]['blink'])//60}:{int(G[g]['blink'])%60:02d}" for g in groups[0][1] if G[g]["blink"]))
print("new-20 NW@10 median:", st.median([G[g]["nw10"] for g in groups[0][1] if G[g]["nw10"]]))
