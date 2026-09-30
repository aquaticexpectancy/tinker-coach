"""Tinker farming study: you vs 23 Immortal pub Tinkers + 1 pro game -> PDF."""
import json, math, pathlib, statistics as st, subprocess, collections
import numpy as np

HERE = pathlib.Path(__file__).parent
M = json.load(open(HERE / "data" / "metrics.json"))
META = {m["match"]: m for m in json.load(open(HERE / "pub_meta.json"))}
PUBS = [g for g in M if g.startswith("p9")]
ALLREF = PUBS + ["pro"]
ME_C, PRO_C, PUB_C, BAND = "#e0503c", "#2f8fd0", "#8a96a3", "#dfe5eb"
OUT = pathlib.Path(r"C:\Users\docky\Documents\tinker\Tinker_Farming_Study.pdf")


def fmt(t):
    return "—" if t is None else f"{int(t // 60)}:{int(t % 60):02d}"


def q(v, p):
    return float(np.percentile(v, p * 100))


def pct_rank(val, arr, higher_better=True):
    """Share of pub players you are better than."""
    arr = [a for a in arr if a is not None]
    better = sum(1 for a in arr if (val > a if higher_better else val < a))
    ties = sum(1 for a in arr if a == val)
    return round(100 * (better + 0.5 * ties) / len(arr))


def pm(g, key, m):
    return M[g]["permin"][str(m)][key]


# ------------------------------------------------------------ metric table
METRICS = [
    # key, label, getter, higher_better, formatter, group
    ("nw10", "Net worth at 10:00", lambda g: pm(g, "nw", 10), True, lambda v: f"{v:,.0f}", "Outcome"),
    ("nw15", "Net worth at 15:00", lambda g: pm(g, "nw", 15), True, lambda v: f"{v:,.0f}", "Outcome"),
    ("nw20", "Net worth at 20:00", lambda g: pm(g, "nw", 20), True, lambda v: f"{v:,.0f}", "Outcome"),
    ("lh10", "Last hits at 10:00", lambda g: pm(g, "lh", 10), True, lambda v: f"{v:.0f}", "Outcome"),
    ("lvl10", "Level at 10:00", lambda g: pm(g, "lvl", 10), True, lambda v: f"{v:.0f}", "Outcome"),
    ("lvl15", "Level at 15:00", lambda g: pm(g, "lvl", 15), True, lambda v: f"{v:.0f}", "Outcome"),
    ("neu10", "Neutral gold at 10:00", lambda g: pm(g, "neu", 10), True, lambda v: f"{v:,.0f}", "Outcome"),
    ("lane10", "Lane-creep gold at 10:00", lambda g: pm(g, "lane", 10), True, lambda v: f"{v:,.0f}", "Outcome"),
    ("first_neu", "First jungle kill after Keen TP", lambda g: M[g]["first_neutral_after_keen"], False, fmt, "Timing"),
    ("first_keen", "First Keen Teleport", lambda g: M[g]["first_keen"], False, fmt, "Timing"),
    ("first_anc", "First ancient kill", lambda g: M[g]["first_ancient"], False, fmt, "Timing"),
    ("blink", "First Blink use", lambda g: M[g]["blink_first"], False, fmt, "Timing"),
    ("blink_nw", "Net worth at first Blink use", lambda g: M[g]["blink_nw"], False, lambda v: f"{v:,.0f}", "Timing"),
    ("kpm", "Creeps killed per March (5–20)", lambda g: M[g]["kpm_5_20"], True, lambda v: f"{v:.2f}", "Efficiency"),
    ("kpt", "Creeps per farm trip (5–20)", lambda g: M[g]["kills_per_farm_trip"], True, lambda v: f"{v:.1f}", "Efficiency"),
    ("triplen", "Average farm trip length", lambda g: M[g]["avg_trip_len"], None, lambda v: f"{v:.1f}s", "Efficiency"),
    ("mpt", "Marches per farm trip", lambda g: M[g]["marches_per_farm_trip"], None, lambda v: f"{v:.2f}", "Efficiency"),
    ("empty", "Farm trips with 0 kills (5–20)", lambda g: M[g]["empty_trips_5_20"], False, lambda v: f"{v:.0f}", "Efficiency"),
    ("gaps40", "No-farm gaps > 40 s (5–20)", lambda g: M[g]["gaps_over_40"], False, lambda v: f"{v:.0f}", "Efficiency"),
    ("anc20", "Ancient creeps killed by 20:00", lambda g: M[g]["ancient_kills_20"], True, lambda v: f"{v:.0f}", "Efficiency"),
    ("stacks", "Camps stacked by 20:00", lambda g: M[g]["stacks_20"], True, lambda v: f"{v:.0f}", "Efficiency"),
    ("dwell", "Fountain stop length (median)", lambda g: M[g]["median_dwell"], False, lambda v: f"{v:.1f}s", "Fountain"),
    ("to_rearm", "Landing → Rearm at fountain", lambda g: M[g]["fountain_to_rearm"], False, lambda v: f"{v:.1f}s", "Fountain"),
    ("bottles", "Bottle presses before Rearm", lambda g: M[g]["fountain_bottles_before_rearm"], False, lambda v: f"{v:.1f}", "Fountain"),
    ("base", "Time at base 5–20 min", lambda g: M[g]["base_time_5_20"], False, lambda v: f"{v:.0f}s", "Fountain"),
    ("lowmana", "Time under 20% mana 5–20", lambda g: M[g]["lowmana_5_20"], False, lambda v: f"{v:.0f}s", "Fountain"),
    ("deaths", "Deaths before 20:00", lambda g: M[g]["deaths_20"], False, lambda v: f"{v:.0f}", "Risk"),
    ("enemy", "Jungle kills on enemy side (5–20)", lambda g: 100 * M[g]["enemy_side_neutral_share_5_20"], None, lambda v: f"{v:.0f}%", "Risk"),
]


def val(key, g):
    for k, _, f, *_ in METRICS:
        if k == key:
            return f(g)


stats = {}
for key, label, f, hb, fm, grp in METRICS:
    arr = [f(g) for g in PUBS if f(g) is not None]
    me = f("me")
    stats[key] = dict(label=label, me=me, pro=f("pro"), arr=arr, p25=q(arr, .25), med=q(arr, .5), p75=q(arr, .75),
                      hb=hb, fm=fm, grp=grp, pct=(pct_rank(me, arr, hb) if hb is not None and me is not None else None))

# correlations with net worth at 15 across all reference games
def spearman(a, b):
    ra = np.argsort(np.argsort(a)); rb = np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])

CORR_KEYS = ["first_neu", "first_anc", "kpm", "kpt", "dwell", "base", "lowmana", "anc20", "empty", "gaps40", "deaths", "lane10", "stacks"]
corr = []
nw15 = [val("nw15", g) for g in ALLREF]
for k in CORR_KEYS:
    xs = [val(k, g) for g in ALLREF]
    pairs = [(x, y) for x, y in zip(xs, nw15) if x is not None]
    r = spearman([p[0] for p in pairs], [p[1] for p in pairs])
    corr.append((k, r, len(pairs)))

# simple effect sizes (linear fit) for the three habits we recommend changing
def slope(k):
    xs = np.array([val(k, g) for g in ALLREF], float); ys = np.array(nw15, float)
    ok = ~np.isnan(xs)
    return float(np.polyfit(xs[ok], ys[ok], 1)[0])

slope_first_neu = slope("first_neu") * 60   # gold per minute of delay
slope_first_anc = slope("first_anc") * 60
slope_kpm = slope("kpm") * 0.5              # gold per +0.5 kills/March

# top quartile by NW15 among pubs
top = sorted(PUBS, key=lambda g: -val("nw15", g))[:6]


# ------------------------------------------------------------ SVG helpers
def band_chart(title, key, ylab="", W=820, H=250):
    P = 50
    xs = list(range(21))
    arr = np.array([[pm(g, key, m) for m in xs] for g in PUBS], float)
    p25, med, p75 = np.percentile(arr, 25, 0), np.percentile(arr, 50, 0), np.percentile(arr, 75, 0)
    me = [pm("me", key, m) for m in xs]; pro = [pm("pro", key, m) for m in xs]
    mx = max(arr.max(), max(me), max(pro)) * 1.05
    X = lambda m: P + m * (W - P - 20) / 20
    Y = lambda v: H - 30 - v / mx * (H - 60)
    o = [f'<svg viewBox="0 0 {W} {H}" class="chart"><text x="{P}" y="18" class="ct">{title}</text>']
    for m in range(0, 21, 5):
        o.append(f'<line x1="{X(m)}" y1="28" x2="{X(m)}" y2="{H-30}" stroke="#e6e9ec"/><text x="{X(m)}" y="{H-12}" class="ax" text-anchor="middle">{m}:00</text>')
    for frac in (0.25, 0.5, 0.75, 1.0):
        v = mx * frac
        o.append(f'<text x="{P-6}" y="{Y(v)+4}" class="ax" text-anchor="end">{v:,.0f}</text><line x1="{P}" y1="{Y(v)}" x2="{W-20}" y2="{Y(v)}" stroke="#f1f3f5"/>')
    poly = " ".join(f"{X(m):.1f},{Y(v):.1f}" for m, v in zip(xs, p75)) + " " + " ".join(f"{X(m):.1f},{Y(v):.1f}" for m, v in reversed(list(zip(xs, p25))))
    o.append(f'<polygon points="{poly}" fill="{BAND}"/>')
    line = lambda vals, c, w, dash="": f'<polyline points="{" ".join(f"{X(m):.1f},{Y(v):.1f}" for m, v in zip(xs, vals))}" fill="none" stroke="{c}" stroke-width="{w}" {dash}/>'
    o.append(line(med, PUB_C, 2, 'stroke-dasharray="5 4"'))
    o.append(line(pro, PRO_C, 2.5))
    o.append(line(me, ME_C, 3))
    o.append(f'<g class="lg"><rect x="{W-300}" y="8" width="12" height="10" fill="{BAND}"/><text x="{W-284}" y="17">Immortal pubs P25–P75</text>'
             f'<line x1="{W-150}" y1="13" x2="{W-134}" y2="13" stroke="{PUB_C}" stroke-width="2" stroke-dasharray="4 3"/><text x="{W-130}" y="17">median</text>'
             f'<line x1="{W-80}" y1="13" x2="{W-66}" y2="13" stroke="{ME_C}" stroke-width="3"/><text x="{W-62}" y="17">you</text></g>'
             f'<g class="lg"><line x1="{W-80}" y1="29" x2="{W-66}" y2="29" stroke="{PRO_C}" stroke-width="3"/><text x="{W-62}" y="33">pro</text></g>')
    o.append("</svg>")
    return "".join(o)


def strip(key, W=820, H=46):
    s = stats[key]; arr = s["arr"]
    vals = arr + [s["me"], s["pro"]]
    lo, hi = min(vals), max(vals)
    if hi == lo: hi = lo + 1
    pad = (hi - lo) * 0.08; lo -= pad; hi += pad
    L, R = 250, W - 70
    X = lambda v: L + (v - lo) / (hi - lo) * (R - L)
    o = [f'<svg viewBox="0 0 {W} {H}" class="strip"><text x="0" y="{H/2+4}" class="sl">{s["label"]}</text>',
         f'<rect x="{X(s["p25"]):.1f}" y="{H/2-9}" width="{max(2, X(s["p75"])-X(s["p25"])):.1f}" height="18" fill="{BAND}" rx="3"/>',
         f'<line x1="{X(s["med"]):.1f}" y1="{H/2-11}" x2="{X(s["med"]):.1f}" y2="{H/2+11}" stroke="{PUB_C}" stroke-width="2"/>']
    for i, v in enumerate(arr):
        o.append(f'<circle cx="{X(v):.1f}" cy="{H/2 + ((i % 3) - 1) * 4:.1f}" r="3" fill="{PUB_C}" opacity=".55"/>')
    o.append(f'<circle cx="{X(s["pro"]):.1f}" cy="{H/2}" r="6" fill="{PRO_C}" stroke="#fff" stroke-width="1.5"/>')
    o.append(f'<circle cx="{X(s["me"]):.1f}" cy="{H/2}" r="7" fill="{ME_C}" stroke="#fff" stroke-width="1.5"/>')
    o.append(f'<text x="{W-62}" y="{H/2+4}" class="sv" fill="{ME_C}">{s["fm"](s["me"])}</text></svg>')
    return "".join(o)


LIM = 8300
def heat(points, title, color, S=380, cells=34):
    grid = np.zeros((cells, cells))
    for x, y in points:
        i = int((x + LIM) / (2 * LIM) * cells); j = int((LIM - y) / (2 * LIM) * cells)
        if 0 <= i < cells and 0 <= j < cells:
            grid[j, i] += 1
    mx = grid.max() or 1
    c = S / cells
    o = [f'<svg viewBox="0 0 {S} {S}" width="{S}" height="{S}" class="map"><rect width="{S}" height="{S}" fill="#101418"/>']
    for x, y in BG[::3]:
        X = (x + LIM) / (2 * LIM) * S; Y = (LIM - y) / (2 * LIM) * S
        o.append(f'<rect x="{X:.0f}" y="{Y:.0f}" width="2" height="2" fill="#2a323a"/>')
    for j in range(cells):
        for i in range(cells):
            if grid[j, i]:
                a = 0.15 + 0.85 * (grid[j, i] / mx) ** 0.6
                o.append(f'<rect x="{i*c:.1f}" y="{j*c:.1f}" width="{c:.1f}" height="{c:.1f}" fill="{color}" opacity="{a:.2f}"/>')
    for (bx, by, col) in ((-6900, -6400, "#1f5130"),):
        X = (bx + LIM) / (2 * LIM) * S; Y = (LIM - by) / (2 * LIM) * S
        o.append(f'<circle cx="{X:.0f}" cy="{Y:.0f}" r="{S*0.05:.0f}" fill="{col}"/><text x="{X:.0f}" y="{Y+4:.0f}" class="ms" text-anchor="middle">base</text>')
    o.append(f'<text x="8" y="18" class="mt">{title}</text></svg>')
    return "".join(o)


def radiant_view(g, x, y):
    return (x, y) if M[g]["team"] == 2 else (-x, -y)

BG = []
for g in ALLREF + ["me"]:
    for t, x, y, life in M[g]["path"][::6]:
        BG.append(radiant_view(g, x, y))

def neutral_pts(games, a, b):
    pts = []
    for g in games:
        for t, kind, name, x, y in M[g]["kills"]:
            if kind == "N" and a * 60 <= t < b * 60:
                pts.append(radiant_view(g, x, y))
    return pts


def path_map(g, a, b, color, title, S=380):
    o = [f'<svg viewBox="0 0 {S} {S}" width="{S}" height="{S}" class="map"><rect width="{S}" height="{S}" fill="#101418"/>']
    for x, y in BG[::3]:
        X = (x + LIM) / (2 * LIM) * S; Y = (LIM - y) / (2 * LIM) * S
        o.append(f'<rect x="{X:.0f}" y="{Y:.0f}" width="2" height="2" fill="#2a323a"/>')
    P = [(t, *radiant_view(g, x, y), life) for t, x, y, life in M[g]["path"] if a * 60 <= t < b * 60 and life == 0]
    seg = []
    for p0, p1 in zip(P, P[1:]):
        if math.hypot(p1[1] - p0[1], p1[2] - p0[2]) < 700:
            X0 = (p0[1] + LIM) / (2 * LIM) * S; Y0 = (LIM - p0[2]) / (2 * LIM) * S
            X1 = (p1[1] + LIM) / (2 * LIM) * S; Y1 = (LIM - p1[2]) / (2 * LIM) * S
            seg.append(f"M{X0:.1f},{Y0:.1f}L{X1:.1f},{Y1:.1f}")
        else:
            X1 = (p1[1] + LIM) / (2 * LIM) * S; Y1 = (LIM - p1[2]) / (2 * LIM) * S
            o.append(f'<path d="M{X1:.1f},{Y1-4:.1f}l4,4l-4,4l-4,-4z" fill="#fff" opacity=".5"/>')
    o.append(f'<path d="{"".join(seg)}" stroke="{color}" stroke-width="2" fill="none" opacity=".9"/>')
    for t, kind, name, x, y in M[g]["kills"]:
        if a * 60 <= t < b * 60:
            x, y = radiant_view(g, x, y)
            X = (x + LIM) / (2 * LIM) * S; Y = (LIM - y) / (2 * LIM) * S
            o.append(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="2.4" fill="{"#7bd66b" if kind == "N" else "#f0a93a"}"/>')
    nN = sum(1 for k in M[g]["kills"] if a * 60 <= k[0] < b * 60 and k[1] == "N")
    nL = sum(1 for k in M[g]["kills"] if a * 60 <= k[0] < b * 60 and k[1] == "L")
    o.append(f'<text x="8" y="18" class="mt">{title}</text><text x="8" y="{S-10}" class="ms">jungle {nN} · lane {nL}</text></svg>')
    return "".join(o)


# ------------------------------------------------------------ text helpers
def row(key):
    s = stats[key]
    pct = "" if s["pct"] is None else f'{s["pct"]}%'
    cls = "" if s["pct"] is None else ("good" if s["pct"] >= 60 else ("bad" if s["pct"] <= 30 else ""))
    return (f'<tr><td>{s["label"]}</td><td class="me">{s["fm"](s["me"])}</td><td>{s["fm"](s["p25"])} – {s["fm"](s["p75"])}</td>'
            f'<td>{s["fm"](s["med"])}</td><td class="pro">{s["fm"](s["pro"])}</td><td class="{cls}">{pct}</td></tr>')


def table(group):
    return ("<table class='mt'><tr><th>Metric</th><th>You</th><th>Pubs P25–P75</th><th>Pub median</th><th>Pro</th><th>Better than</th></tr>"
            + "".join(row(k) for k, *_rest, g in METRICS if g == group) + "</table>")


CN = {k: stats[k]["label"] for k in stats}
corr_rows = "".join(
    f'<tr><td>{CN[k]}</td><td><div class="bar" style="width:{abs(r)*160:.0f}px;background:{"#3a9d5d" if r > 0 else "#d05a47"}"></div></td><td>{r:+.2f}</td></tr>'
    for k, r, n in sorted(corr, key=lambda c: -abs(c[1])))

me_fount = M["me"]["fountain_seqs"]; pro_fount = M["pro"]["fountain_seqs"]
pub_fount = [s for g in PUBS for s in M[g]["fountain_seqs"]]
fc = lambda seqs: collections.Counter(seqs).most_common(4)
fount_rows = lambda seqs, n: "".join(f"<tr><td class='mono'>{s}</td><td>{c}</td><td>{100*c/max(1,len(seqs)):.0f}%</td></tr>" for s, c in fc(seqs)[:n])

sample_rows = "".join(
    f"<tr><td>{g[1:]}</td><td>{'W' if META[int(g[1:])]['win'] else 'L'}</td><td>{META[int(g[1:])]['dur']//60}</td>"
    f"<td>{META[int(g[1:])]['k']}/{META[int(g[1:])]['d']}/{META[int(g[1:])]['a']}</td><td>{pm(g,'lh',10)}</td><td>{pm(g,'nw',10):,}</td><td>{pm(g,'nw',15):,}</td>"
    f"<td>{fmt(M[g]['first_neutral_after_keen'])}</td><td>{fmt(M[g]['first_ancient'])}</td><td>{M[g]['kpm_5_20']:.2f}</td><td>{M[g]['median_dwell']:.1f}s</td></tr>"
    for g in sorted(PUBS, key=lambda g: -pm(g, 'nw', 15)))

S = stats
wins = sum(1 for g in PUBS if META[int(g[1:])]["win"])
top_first_neu = st.median(M[g]["first_neutral_after_keen"] for g in top)
top_first_anc = st.median(M[g]["first_ancient"] for g in top)
top_dwell = st.median(M[g]["median_dwell"] for g in top)
top_nw15 = st.median(val("nw15", g) for g in top)
corr_d = {k: r for k, r, n in corr}

shots = [
    ("0550", "5:50 — first minute with Keen Teleport",
     "You're back in mid lane waiting on a wave (28 LH, lvl 6). The pro used his first Keen Teleport to go straight into the Radiant jungle and is already Rearming mid-camp."),
    ("0730", "7:30 — level 6 vs level 8",
     "You're finally in the jungle (39 LH). The pro is resetting at fountain after clearing an ancient camp and a hard camp (57 LH)."),
    ("1000", "10:00 — 81 vs 95 LH, level 9 vs 11",
     "HUD crop: the pro already has Deploy Turrets skilled and two more levels. Your gap here is all neutral gold (723 vs 1,451); your lane gold is higher."),
    ("1200", "12:00 — Rearm on an empty tank",
     "You channel Rearm with 108/987 mana in the jungle, forcing another fountain trip right after."),
    ("1350", "13:50 — fighting while he farms",
     "You're in a river fight inside Necrophos' ult; 0 creeps between 13:33 and 15:19. The pro is refilling at fountain between farm trips."),
    ("1500", "15:00 — 148 vs 180 LH, level 12 vs 15",
     "He has nearly double your current mana (1,070 vs 567)."),
]
shot_html = "".join(
    f'<div class="shot"><h4>{t}</h4><img src="report_assets/pair_{m}.jpg"><img class="hud" src="report_assets/hud_{m}.jpg"><p>{c}</p></div>'
    for m, t, c in shots)

FIXES = [
    ("Get into the jungle as soon as Keen Teleport is up",
     f"Your first jungle kill after getting Keen Teleport came at <b>{fmt(S['first_neu']['me'])}</b>. Immortal pub median is <b>{fmt(S['first_neu']['med'])}</b>, the top-6 farmers "
     f"<b>{fmt(top_first_neu)}</b>, the pro {fmt(S['first_neu']['pro'])}. You're later than {100 - S['first_neu']['pct']}% of the sample. "
     f"Between 5:35 and 7:25 you teleported between fountain and mid 7 times and killed ~11 creeps. "
     f"Across the sample, a later first jungle kill goes with lower net worth at 15:00 (Spearman r = {corr_d['first_neu']:+.2f}; linear fit ≈ {abs(slope_first_neu):,.0f} gold per minute of delay).",
     ["Do what every top-10 transition in the sample did: push the wave, Keen to fountain, Rearm, then Keen <b>straight into the camp pair next to mid</b>. Don't go fountain → mid → fountain → mid.",
      "Pre-5:00: shove mid, then March the medium camp beside mid lane so it's already part of your route.",
      "Benchmark: first neutral gold before 6:30, and 300+ neutral gold by 7:30."]),
    ("Put the ancient camp in your loop by ~9:00",
     f"First ancient kill: you <b>{fmt(S['first_anc']['me'])}</b>, pub median <b>{fmt(S['first_anc']['med'])}</b>, top-6 {fmt(top_first_anc)}, pro {fmt(S['first_anc']['pro'])}. "
     f"Ancient creeps by 20:00: you {S['anc20']['me']:.0f}, pub median {S['anc20']['med']:.0f}, pro {S['anc20']['pro']:.0f}. "
     f"Ancients give the most gold <i>and</i> XP per March: that's a big part of the pro's 2-level lead at 10:00.",
     ["From level 7–8, pair your side's hard camp with the ancient camp next to it (on Radiant: the top-side hard camp + ancient).",
      "Two Marches from behind the ancient camp, Laser the last creep, TP out.",
      "Benchmark: ancient cleared at least once before 9:30."]),
    ("Cut fountain stops to 7 seconds",
     f"Median fountain stop: you <b>{S['dwell']['me']:.1f} s</b>, pub median {S['dwell']['med']:.1f} s, pro {S['dwell']['pro']:.1f} s. You're slower than "
     f"{100 - S['dwell']['pct']}% of the sample. The cause is visible in the cast order: you press Bottle {S['bottles']['me']:.1f}× before Rearm "
     f"(pubs {S['bottles']['med']:.1f}×, pro {S['bottles']['pro']:.1f}×) and wait {S['to_rearm']['me']:.1f} s after landing before Rearming (pubs {S['to_rearm']['med']:.1f} s). "
     f"Your most common fountain sequence is <span class='mono'>{fc(me_fount)[0][0]}</span>; the pro's is <span class='mono'>{fc(pro_fount)[0][0]}</span>. "
     f"Total time at base 5–20 min: you {S['base']['me']:.0f} s vs pub median {S['base']['med']:.0f} s. That's about a minute of lost farm.",
     ["At most <b>one</b> Bottle press on landing, then Rearm straight away. The rest of the refill happens during the Rearm channel.",
      f"Pattern to drill (the most common Immortal sequence, {100*fc(pub_fount)[0][1]/len(pub_fount):.0f}% of their stops): <span class='mono'>land → b → R → b → K</span>. The pro often skips the Bottle entirely: <span class='mono'>b R K</span>."]),
    ("Stop running your mana dry",
     f"You spent <b>{S['lowmana']['me']:.0f} s</b> under 20% mana between 5 and 20 min (pub median {S['lowmana']['med']:.0f} s, pro {S['lowmana']['pro']:.0f} s). "
     f"Your farm trips are short ({S['triplen']['me']:.1f} s vs pub median {S['triplen']['med']:.1f} s) with {S['mpt']['me']:.1f} Marches each. You empty the tank on one spot and have to go home. "
     f"At 12:00 the screenshot shows you channelling Rearm with 108/987 mana.",
     ["Leave fountain full, and spend the mana over <b>two</b> nearby camps (or a wave + a camp) instead of 3 Marches on one.",
      "If you're under ~300 mana, don't Rearm in the jungle; Keen TP home first."]),
    ("Keep the efficiency you already have, but aim Marches better",
     f"Good news: your creeps per trip ({S['kpt']['me']:.1f}) is <b>above</b> the pub median ({S['kpt']['med']:.1f}), and you had only {S['empty']['me']:.0f} empty farm trips "
     f"(pubs {S['empty']['med']:.0f}). Per March you get {S['kpm']['me']:.2f} kills (pubs {S['kpm']['med']:.2f}, pro {S['kpm']['pro']:.2f}). "
     f"In 5–10 min, 20 of your 30 jungle kills came from a single camp; the pro spread his over 6 camps.",
     ["Cast March from <b>behind</b> the camp so the robots walk through it; 1 March for a medium camp, 2 for hard/ancient.",
      "Finish the last creep with Laser instead of a third March (pro pattern <span class='mono'>B M R M L</span>)."]),
    ("Don't give up farm for fights you don't need, and don't farm the enemy jungle",
     f"From 13:33 to 15:19 you had two no-farm gaps of 53 s and 56 s while fighting in the river (screenshot 13:50). "
     f"{S['enemy']['me']:.0f}% of your jungle kills 5–20 were on the enemy side (pub median {S['enemy']['med']:.0f}%, pro {S['enemy']['pro']:.0f}%). "
     f"Credit where it's due: 0 deaths before 20:00 (pub median {S['deaths']['med']:.0f}), one of only three Tinkers in the sample who didn't die before 20:00.",
     ["When you do join a fight, March a wave or camp on the way out so the TP cycle still earns gold.",
      "Stay on your side of the map until you have Blink + a defensive item."]),
    ("Blink timing is fine (not a mistake)",
     f"First Blink use: you {fmt(S['blink']['me'])}, earlier than {S['blink']['pct']}% of the pubs (median {fmt(S['blink']['med'])}); only the pro was much earlier ({fmt(S['blink']['pro'])}). "
     f"Net worth at that moment: you {S['blink_nw']['me']:,.0f}, pub median {S['blink_nw']['med']:,.0f}. Everyone gets Blink at roughly the same <i>net worth</i>, so the clock "
     f"time just follows your farm speed. (This is first use, not purchase time.)",
     ["No build change needed. Fixes 1–4 move Blink earlier on their own."]),
]
fix_html = "".join(
    f'<div class="mist"><h3><span class="num">{i}</span>{t}</h3><p>{ev}</p><ul class="fix">{"".join(f"<li>{x}</li>" for x in fx)}</ul></div>'
    for i, (t, ev, fx) in enumerate(FIXES, 1))

strips = lambda keys: "".join(strip(k) for k in keys)

html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Tinker Farming Study</title><style>
@page {{ size: A4; margin: 13mm 12mm; }}
body {{ font-family: 'Segoe UI', Arial, sans-serif; color:#1b1f24; font-size:11.3px; line-height:1.5; margin:0; }}
h1 {{ font-size:30px; margin:0 0 2px; }} h2 {{ font-size:19px; margin:20px 0 8px; border-bottom:2px solid #1b1f24; padding-bottom:3px; }}
h3 {{ font-size:14px; margin:12px 0 5px; }} h4 {{ margin:8px 0 4px; font-size:12.5px; }}
.sub {{ color:#5b6570; }} .me {{ color:{ME_C}; font-weight:700; }} .pro {{ color:{PRO_C}; font-weight:700; }}
.pb {{ page-break-before:always; }} .box {{ background:#f4f6f8; border-radius:6px; padding:10px 14px; margin:8px 0; }}
.kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:8px; margin:12px 0; }}
.kpi {{ border:1px solid #d7dce1; border-radius:6px; padding:8px 10px; font-size:10.5px; color:#5b6570; }} .kpi b {{ font-size:18px; display:block; color:#1b1f24; }}
table {{ border-collapse:collapse; width:100%; font-size:10.3px; margin:4px 0 10px; }} th,td {{ border-bottom:1px solid #e3e6ea; padding:3px 6px; text-align:right; }}
th {{ background:#f2f4f6; }} td:first-child, th:first-child {{ text-align:left; }}
td.good {{ color:#2e8b57; font-weight:700; }} td.bad {{ color:{ME_C}; font-weight:700; }}
.chart {{ width:100%; height:auto; margin:4px 0; }} .ct {{ font:700 13px 'Segoe UI'; }} .ax {{ font:10px 'Segoe UI'; fill:#7a848e; }} .lg text {{ font:10px 'Segoe UI'; fill:#444; }}
.strip {{ width:100%; height:auto; display:block; }} .sl {{ font:11px 'Segoe UI'; fill:#1b1f24; }} .sv {{ font:700 11px 'Segoe UI'; }}
.maps {{ display:flex; gap:10px; justify-content:center; flex-wrap:wrap; page-break-inside:avoid; margin:6px 0; }}
.map {{ border-radius:6px; }} .mt {{ fill:#fff; font:700 12.5px 'Segoe UI'; }} .ms {{ fill:#c9d1d9; font:10.5px 'Segoe UI'; }}
.mist {{ border-left:4px solid {ME_C}; padding:2px 0 2px 12px; margin:12px 0; page-break-inside:avoid; }}
.num {{ display:inline-block; background:{ME_C}; color:#fff; border-radius:50%; width:20px; height:20px; text-align:center; line-height:20px; margin-right:8px; font-size:12px; }}
.fix {{ margin:4px 0 0; padding-left:18px; }} .fix li {{ margin:2px 0; }} .fix li::marker {{ content:'✔  '; color:#2e8b57; }}
.bar {{ height:10px; border-radius:2px; display:inline-block; }}
.mono {{ font-family:Consolas,monospace; }}
.shot {{ page-break-inside:avoid; margin-bottom:12px; }} .shot img {{ width:100%; display:block; border-radius:4px; margin-bottom:4px; }} .shot img.hud {{ width:80%; }}
.cols {{ display:grid; grid-template-columns:1fr 1fr 1fr; gap:12px; }} .legend span {{ margin-right:14px; }}
.dot {{ display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:4px; vertical-align:middle; }}
</style></head><body>

<h1>Tinker Farming Study</h1>
<div class="sub">How your Tinker farms minutes 0–20, compared with <b>{len(PUBS)} Immortal public matches</b> and one professional match. Patch 7.41. Replays parsed tick by tick.</div>

<div class="kpis">
<div class="kpi">Your match<b>9016088490</b>Tinker mid · Radiant · loss · 0/4/8</div>
<div class="kpi">Reference sample<b>{len(PUBS)} Immortal pubs</b>{wins} wins / {len(PUBS)-wins} losses · 28–47 min</div>
<div class="kpi">Pro reference<b>NothingToSay</b>Games of the Future 2026 · win</div>
<div class="kpi">Your net worth @15<b class="me">{S['nw15']['me']:,.0f}</b>better than {S['nw15']['pct']}% of the pubs</div>
</div>

<h2>Summary</h2>
<div class="box">
<p><b>Your farm isn't bad, and that matters.</b> Against the Immortal pub Tinkers your 10:00 and 15:00 net worth sit around the middle of the pack
(better than {S['nw10']['pct']}% at 10:00 and {S['nw15']['pct']}% at 15:00), your lane farm is strong (lane gold at 10:00 better than {S['lane10']['pct']}%),
and you didn't die once before 20:00. Measured against only the pro game you'd look far worse than you are: he is the best farmer in this entire dataset.</p>
<p><b>Where you lose gold</b> is three habits that show up clearly against the whole sample, not just the pro:</p>
<ol>
<li><b>Late transition to the jungle</b>: first jungle kill after Keen Teleport at {fmt(S['first_neu']['me'])} (pub median {fmt(S['first_neu']['med'])}; later than {100-S['first_neu']['pct']}% of the sample).</li>
<li><b>Late ancients</b>: first ancient at {fmt(S['first_anc']['me'])} (pub median {fmt(S['first_anc']['med'])}); {S['anc20']['me']:.0f} ancient creeps by 20:00 vs a median of {S['anc20']['med']:.0f}.</li>
<li><b>Slow fountain stops and dry mana</b>: {S['dwell']['me']:.1f} s per stop (slower than {100-S['dwell']['pct']}% of the sample), Bottle pressed before Rearm, and {S['lowmana']['me']:.0f} s under 20% mana.</li>
</ol>
<p>The top-6 farmers in the sample average {top_nw15:,.0f} net worth at 15:00; you have {S['nw15']['me']:,.0f}, a gap of about {top_nw15 - S['nw15']['me']:,.0f}.
Using the trends from section 2.6 as a rough guide, your {fmt(M['me']['first_neutral_after_keen'] - top_first_neu)} later jungle start is worth ~{abs(slope_first_neu) * (M['me']['first_neutral_after_keen'] - top_first_neu) / 60:,.0f} gold
and your {fmt(M['me']['first_ancient'] - top_first_anc)} later first ancient ~{abs(slope_first_anc) * (M['me']['first_ancient'] - top_first_anc) / 60:,.0f} gold. The two estimates overlap, but together they roughly cover the gap.
Slow fountain stops are harder to put a number on, but they are the single strongest habit signal in the data.</p>
</div>

{band_chart("Net worth, 0–20 min", "nw")}
{band_chart("Gold from neutral camps, 0–20 min", "neu")}
<p class="sub">You track the Immortal median here, but only from 8:00; the pro, and the best pubs, start 2–3 minutes earlier and keep pulling away.</p>

<h2 class="pb">1 · Method</h2>
<h3>Data</h3>
<ul>
<li><b>Your game</b>: match 9016088490 (Radiant Tinker mid, 33:41, loss).</li>
<li><b>Pub sample</b>: ranked public matches played on 28 Sep 2026 (OpenDota database) with average MMR ≥ Divine 5 and a Tinker in them, lasting 28–50 min. From this list,
the <b>first {len(PUBS)+1} games with an Immortal Tinker were taken in order</b>, without looking at the result (1 replay failed to download). That leaves {len(PUBS)} games, {wins} won and {len(PUBS)-wins} lost.
All {len(PUBS)} Tinkers played mid (they were in mid lane 85–100% of the time between 1:30 and 5:00).</li>
<li><b>Pro game</b>: match 8924616191, NothingToSay (Xtreme Gaming) vs Rekonix, 33:30, win. Kept as a single reference line, not part of the statistics.</li>
<li>All games are patch 7.41. The replays (.dem) come from Valve's replay servers and were parsed with the Clarity 4 parser. Every 0.5 s the parser recorded Tinker's position, HP, mana, level,
last hits, net worth, gold by source and camps stacked. It also recorded every spell/item cast and every creep death, including where the creep died.</li>
</ul>
<h3>Definitions</h3>
<ul>
<li><b>Farm trip</b>: from the moment Tinker lands after a Keen Teleport (detected by a position jump &gt; 1,200 units) to the next landing. A trip that lands in base is a <b>fountain stop</b>.</li>
<li><b>Creep kill</b>: a lane or neutral creep whose killing blow came from Tinker (Laser, March, attack, Turrets). A kill is "jungle" or "lane" by creep type, and located where the creep died.</li>
<li><b>Ancient</b>: drakes/dragons, thunder lizards, golems (not mud golems), prowlers, frostbitten golems/ice shamans.</li>
<li><b>Enemy side</b>: the half of the map across the river diagonal. For the maps, Dire games are mirrored so every Tinker is shown as if playing Radiant.</li>
<li><b>Percentile</b> (“better than X%”): share of the {len(PUBS)} pub Tinkers you did better than on that metric (ties count half).</li>
</ul>
<h3>Limitations</h3>
<ul>
<li>One game of yours. Some of these numbers will move from game to game; habits (fountain sequence, when you go to the jungle) usually don't.</li>
<li>Your game is at a much lower MMR than the sample. Lanes and jungle are usually less contested there, so matching the Immortal <i>median</i> is not the ceiling.</li>
<li>Correlations across {len(ALLREF)} games describe patterns, not proof of cause. Game state (kills, pressure) also affects farm.</li>
<li>Blink timing is first <i>use</i>, not purchase time.</li>
</ul>

<h2 class="pb">2 · Results</h2>
<p>Each row puts you (red), the pro (blue) and every pub Tinker (grey dots) on one axis. The shaded band is the middle 50% of the pubs; the vertical tick is the median.</p>
<h3>2.1 Outcome</h3>
{strips(["nw10","nw15","nw20","lh10","lvl10","lvl15","neu10","lane10"])}
{table("Outcome")}
<h3>2.2 Timing of the transition to the jungle</h3>
{strips(["first_keen","first_neu","first_anc","blink","blink_nw"])}
{table("Timing")}
<p>Everyone gets Keen Teleport at about the same time. What differs is what they do with it. Most Immortal Tinkers kill their first jungle creep within ~1 minute of the first Keen Teleport;
you took about 2 minutes. Ancients show the biggest spread of any timing metric.</p>

<h3 class="pb">2.3 Farming efficiency</h3>
{strips(["kpm","kpt","triplen","mpt","empty","gaps40","anc20","stacks"])}
{table("Efficiency")}
<p>Your trips are <b>short and dense</b>: more creeps per trip than most pubs, but shorter trips, with more Marches on a single spot and then home.
Top farmers spend a little longer per trip and chain two camps (or a wave and a camp) before going back.</p>

<h3>2.4 Fountain behaviour and mana</h3>
{strips(["dwell","to_rearm","bottles","base","lowmana"])}
{table("Fountain")}
<div class="cols">
<div><b class="me">Your fountain stops</b><table><tr><th>Sequence</th><th>n</th><th>%</th></tr>{fount_rows(me_fount, 4)}</table></div>
<div><b class="pro">Pro fountain stops</b><table><tr><th>Sequence</th><th>n</th><th>%</th></tr>{fount_rows(pro_fount, 4)}</table></div>
<div><b>Immortal pubs (all)</b><table><tr><th>Sequence</th><th>n</th><th>%</th></tr>{fount_rows(pub_fount, 4)}</table></div>
</div>
<p class="sub">b = Bottle, R = Rearm, K = Keen Teleport out, M = March. Read left to right from the moment you land.</p>

<h3>2.5 Risk</h3>
{strips(["deaths","enemy"])}
{table("Risk")}

<h3 class="pb">2.6 What goes with high net worth at 15:00</h3>
<p>Spearman rank correlation between each habit and net worth at 15:00 across all {len(ALLREF)} reference games (23 pubs + pro). Green = more of it goes with more gold,
red = more of it goes with less gold. With {len(ALLREF)} games, |r| above ~0.4 is a meaningful pattern and below ~0.2 is noise.</p>
<table style="width:70%"><tr><th>Habit</th><th></th><th>r</th></tr>{corr_rows}</table>
<div class="box">
<b>Observed patterns</b>
<ul>
<li><b>Transition timing matters most.</b> An earlier first jungle kill and an earlier first ancient go with higher 15-minute net worth
(r = {corr_d['first_neu']:+.2f} and {corr_d['first_anc']:+.2f}). As a rough linear fit: about {abs(slope_first_neu):,.0f} gold at 15:00 per minute of delay to the first jungle kill,
and about {abs(slope_first_anc):,.0f} per minute of delay to the first ancient.</li>
<li><b>Ancient volume</b> (r = {corr_d['anc20']:+.2f}) and <b>kills per March</b> (r = {corr_d['kpm']:+.2f}) are the efficiency signals; roughly {slope_kpm:,.0f} gold at 15:00 per +0.5 kills/March.</li>
<li><b>Short fountain stops</b> go with more gold (r = {corr_d['dwell']:+.2f} for the median stop length), one of the strongest signals in the table. Total base time
(r = {corr_d['base']:+.2f}) and low-mana time (r = {corr_d['lowmana']:+.2f}) are not: <i>how often</i> you go home matters less than <i>how long you stand there</i>.</li>
<li><b>Lane gold at 10:00</b> also matters (r = {corr_d['lane10']:+.2f}). This is your strength: you're better than {S['lane10']['pct']}% of the sample.</li>
<li>Empty trips, deaths before 20:00 and total base time show almost no relation to 15-minute net worth in this sample.</li>
</ul></div>

<h2 class="pb">3 · Where the farm happens</h2>
<p>Every jungle creep killed by Tinker, drawn as a density map (brighter = more kills). Dire games are mirrored so everything is shown from the Radiant side (base bottom-left).</p>
<div class="maps">
{heat(neutral_pts(PUBS, 5, 10), "Immortal pubs · jungle kills 5–10 min", "#6fd36a")}
{heat(neutral_pts(["me"], 5, 10), "You · jungle kills 5–10 min", "#ff6a52")}
</div>
<div class="maps">
{heat(neutral_pts(top, 10, 15), "Top-6 farmers · jungle kills 10–15 min", "#6fd36a")}
{heat(neutral_pts(["me"], 10, 15), "You · jungle kills 10–15 min", "#ff6a52")}
</div>
<p>From 5 to 10 min the Immortal Tinkers spread their jungle kills over the camps closest to mid on their own side, including the ancient camp.
Your 5–10 map is almost a single hot spot: one camp next to mid, visited over and over.</p>

<h3>Your routes vs the pro's, minute by minute</h3>
<p class="legend"><span><span class="dot" style="background:{ME_C}"></span>your path</span><span><span class="dot" style="background:{PRO_C}"></span>pro path</span>
<span><span class="dot" style="background:#7bd66b"></span>jungle kill</span><span><span class="dot" style="background:#f0a93a"></span>lane kill</span><span>◇ Keen TP landing</span></p>
<div class="maps">{path_map("me", 5, 8, ME_C, "You 5:00–8:00")}{path_map("pro", 5, 8, PRO_C, "Pro 5:00–8:00")}</div>
<div class="maps">{path_map("me", 8, 12, ME_C, "You 8:00–12:00")}{path_map("pro", 8, 12, PRO_C, "Pro 8:00–12:00")}</div>

<h2 class="pb">4 · Replay screenshots: you vs the pro at the same moments</h2>
<p>Captured in the Dota 2 replay viewer at identical game times, camera locked on Tinker and the hero selected so the HUD shows level, last hits and items. You on the left, pro on the right.</p>
{shot_html}

<h2 class="pb">5 · Mistakes and how to fix them</h2>
<p>Roughly ordered by how much gold they cost you: how strongly the habit goes with net worth (section 2.6) and how far outside the sample you are.</p>
{fix_html}

<h2 class="pb">6 · Practice plan</h2>
<div class="box">
<b>Benchmarks for minutes 5–15</b> (Immortal-pub median / top-6 median in this study):
<table style="width:80%"><tr><th>Checkpoint</th><th>You</th><th>Pub median</th><th>Top-6</th></tr>
<tr><td>First jungle kill after Keen TP</td><td class="me">{fmt(S['first_neu']['me'])}</td><td>{fmt(S['first_neu']['med'])}</td><td>{fmt(top_first_neu)}</td></tr>
<tr><td>First ancient</td><td class="me">{fmt(S['first_anc']['me'])}</td><td>{fmt(S['first_anc']['med'])}</td><td>{fmt(top_first_anc)}</td></tr>
<tr><td>Fountain stop</td><td class="me">{S['dwell']['me']:.1f}s</td><td>{S['dwell']['med']:.1f}s</td><td>{top_dwell:.1f}s</td></tr>
<tr><td>Neutral gold at 10:00</td><td class="me">{S['neu10']['me']:,.0f}</td><td>{S['neu10']['med']:,.0f}</td><td>{st.median(val('neu10', g) for g in top):,.0f}</td></tr>
<tr><td>Net worth at 15:00</td><td class="me">{S['nw15']['me']:,.0f}</td><td>{S['nw15']['med']:,.0f}</td><td>{top_nw15:,.0f}</td></tr>
</table></div>
<h3>Three drills</h3>
<ol>
<li><b>Demo mode (5 min a day)</b>: land in fountain → (one Bottle) → Rearm → Keen TP. Nothing else. Get it under 7 s.</li>
<li><b>First camp within 40 s of Keen Teleport</b>: next 5 games, fountain → camp pair next to mid right after your first Keen TP home. Write down your first neutral-gold time.</li>
<li><b>Ancient by 9:30</b>: once you hit level 7, the ancient camp is part of every second loop.</li>
</ol>
<h3>Review checklist after each game</h3>
<ul><li>Neutral gold at 7:00 &gt; 0? At 10:00 &gt; 1,000?</li><li>Ancient cleared before 9:30?</li><li>How many times did I stand in fountain longer than 8 s?</li><li>Any 40 s+ window with no creeps killed? Why?</li></ul>

<h2 class="pb">Appendix A · The {len(PUBS)} Immortal pub games</h2>
<table><tr><th>Match</th><th>W/L</th><th>Min</th><th>K/D/A</th><th>LH@10</th><th>NW@10</th><th>NW@15</th><th>1st jungle</th><th>1st ancient</th><th>Kills/March</th><th>Fountain</th></tr>
<tr style="background:#fdecea"><td>You · 9016088490</td><td>L</td><td>33</td><td>0/4/8</td><td>{pm('me','lh',10)}</td><td>{pm('me','nw',10):,}</td><td>{pm('me','nw',15):,}</td><td>{fmt(M['me']['first_neutral_after_keen'])}</td><td>{fmt(M['me']['first_ancient'])}</td><td>{M['me']['kpm_5_20']:.2f}</td><td>{M['me']['median_dwell']:.1f}s</td></tr>
<tr style="background:#e8f3fb"><td>Pro · 8924616191</td><td>W</td><td>33</td><td>14/1/16</td><td>{pm('pro','lh',10)}</td><td>{pm('pro','nw',10):,}</td><td>{pm('pro','nw',15):,}</td><td>{fmt(M['pro']['first_neutral_after_keen'])}</td><td>{fmt(M['pro']['first_ancient'])}</td><td>{M['pro']['kpm_5_20']:.2f}</td><td>{M['pro']['median_dwell']:.1f}s</td></tr>
{sample_rows}</table>
<p class="sub">Sorted by net worth at 15:00. Kills/March covers 5–20 min.</p>

<h2>Appendix B · Your farm trips 5:00–10:00 vs the pro</h2>
<p class="sub">Each string is one farm trip, read left to right: M March, R Rearm, L Laser, B Blink, b Bottle, D Deploy Turrets, K Keen Teleport out.</p>
<div class="cols" style="grid-template-columns:1fr 1fr">
<div><b class="me">You</b><p class="mono">{' · '.join(M['me']['trip_seqs'][:14])}</p></div>
<div><b class="pro">Pro</b><p class="mono">{' · '.join(M['pro']['trip_seqs'][:14])}</p></div>
</div>
</body></html>"""

(HERE / "study.html").write_text(html, encoding="utf-8")
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={OUT}",
                (HERE / "study.html").as_uri()], check=True, capture_output=True, timeout=180)
print(OUT, OUT.stat().st_size)
for k in ["nw10", "nw15", "first_neu", "first_anc", "dwell", "lowmana", "kpt", "anc20"]:
    s = stats[k]; print(k, s["fm"](s["me"]), "med", s["fm"](s["med"]), "pct", s["pct"])
print("corr", [(k, round(r, 2)) for k, r, n in corr])
print("slopes", round(slope_first_neu), round(slope_first_anc), round(slope_kpm), "top6 nw15", top_nw15)
