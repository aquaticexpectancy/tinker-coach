"""Your training log: every run the coach recorded, against the Immortal and top-10 benchmarks.

    python stats.py            writes stats.html and opens it in your browser

Reads scoresheet.csv (one row per run, written at 10:00) and runs.csv (one row per game
minute of every run). Benchmarks come from 23 Immortal Tinker games + the top-10 transitions.
"""
import csv
import json
import pathlib
import webbrowser

HERE = pathlib.Path(__file__).parent
DATA = json.loads((HERE / "coach_data.json").read_text(encoding="utf-8"))
OUT = HERE / "stats.html"
PALETTE = ["#e0503c", "#f0a93a", "#9b59b6", "#16a085", "#2f8fd0", "#d35400", "#7f8c8d", "#c0392b"]


def read(name):
    p = HERE / name
    if not p.exists():
        return []
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def secs(t):
    try:
        m, s = t.split(":")
        return int(m) * 60 + int(s)
    except (ValueError, AttributeError):
        return None


def chart(title, runs, key, bench_key, ylabel, W=860, H=300):
    P, R, T, B = 60, 150, 28, 34
    series = {name: [(int(r["minute"]), float(r[key])) for r in rows if r.get(key) not in ("", None)] for name, rows in runs.items()}
    bench = DATA.get(bench_key, {})
    allv = [v for s in series.values() for _, v in s] + [v for arr in bench.values() for v in arr[:21]]
    if not allv:
        return ""
    mx = max(allv) * 1.05
    X = lambda m: P + m / 20 * (W - P - R)
    Y = lambda v: H - B - v / mx * (H - T - B)
    o = [f'<svg viewBox="0 0 {W} {H}" class="chart"><text x="{P}" y="18" class="ct">{title}</text>']
    for m in range(0, 21, 5):
        o.append(f'<line x1="{X(m)}" y1="{T}" x2="{X(m)}" y2="{H-B}" class="grid"/><text x="{X(m)}" y="{H-12}" class="ax" text-anchor="middle">{m}:00</text>')
    for f in (0.25, 0.5, 0.75, 1):
        o.append(f'<text x="{P-6}" y="{Y(mx*f)+4}" class="ax" text-anchor="end">{mx*f:,.0f}</text>')
    for (name, arr), dash in zip(bench.items(), ("5 4", "2 3")):
        pts = " ".join(f"{X(m):.1f},{Y(v):.1f}" for m, v in enumerate(arr[:21]))
        o.append(f'<polyline points="{pts}" fill="none" stroke="#8a96a3" stroke-width="2" stroke-dasharray="{dash}"/>')
        o.append(f'<text x="{X(20)+6}" y="{Y(arr[20])+4}" class="lg" fill="#8a96a3">{"Immortal median" if "immortal" in name else "top-10"}</text>')
    for i, (name, pts_) in enumerate(series.items()):
        if not pts_:
            continue
        col = PALETTE[i % len(PALETTE)]
        pts = " ".join(f"{X(m):.1f},{Y(v):.1f}" for m, v in pts_ if m <= 20)
        o.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="2.5"/>')
        early = [p for p in pts_ if p[0] <= 20]
        if not early:                                  # e.g. an idle lobby logged only after 20:00
            continue
        lm, lv = early[-1]
        o.append(f'<text x="{X(lm)+6}" y="{Y(lv)+4 + 12 * (i % 2)}" class="lg" fill="{col}">{name}</text>')
    o.append("</svg>")
    return "".join(o)


def main():
    score = read("scoresheet.csv")
    minutes = read("runs.csv")
    runs = {}
    SAMPLES = {"9020212922", "9020204172", "9016088490"}           # simulator test data, not your runs
    minutes = [r for r in minutes if r["match"] not in SAMPLES]
    score = [r for r in score if r.get("match") not in SAMPLES]
    done = {r["match"]: ("drill" if (secs(r.get("first_keen")) or 999) < 180 else "game") for r in score}
    for r in minutes:
        if r["match"] in done:
            runs.setdefault(f"{r['session'][5:10].replace('-', '/')} {r['session'][11:13]}:{r['session'][13:15]} {done[r['match']]}", []).append(r)
    targets = {"first_camp_kill": None, "first_ancient": 465, "camp_trips_5_10": 7, "fountain_stops_over_8s": 0,
               "median_fountain_stop": 7.0}
    rows = []
    for i, s in enumerate(score, 1):
        keen, camp = secs(s.get("first_keen")), secs(s.get("first_camp_kill"))
        drill = keen is not None and keen < 180            # Keen learned during a drill's fast-forward
        if drill:
            keen = max(keen, 295)                           # the drill really starts at the 4:55 GO
        switch = (camp - keen) if keen is not None and camp is not None else None
        def cls(ok):
            return "good" if ok else "bad"
        anc = secs(s.get("first_ancient"))
        stops = float(s.get("median_fountain_stop") or 99)
        cells = [
            (s.get("date", ""), ""), (s.get("match", "") + (" · drill" if drill else " · game"), ""),
            (f"{switch} s" if switch is not None else "—", cls(switch is not None and switch <= 40)),
            (s.get("first_ancient", "—"), cls(anc is not None and anc <= 465)),
            (s.get("C_trip_mana", ""), cls(int(s.get("C_trip_mana") or 0) >= 600)),
            (s.get("camp_trips_5_10", ""), cls(int(s.get("camp_trips_5_10") or 0) >= 7)),
            (f"{s.get('median_fountain_stop', '')} s", cls(stops <= 7)),
            (s.get("fountain_stops_over_8s", ""), cls(int(s.get("fountain_stops_over_8s") or 0) == 0)),
            (s.get("home_mana") or "—", "" if not s.get("home_mana") else cls(int(s["home_mana"]) >= 226)),
            (s.get("lh_at_10", "") + (" (from 0 at 5:00)" if drill else ""),
             "" if drill else cls(int(s.get("lh_at_10") or 0) >= DATA["bench_lh"]["top10"][10])),
            (s.get("nw_at_10") or "—", "" if not s.get("nw_at_10") else cls(int(s["nw_at_10"]) >= DATA["bench_nw"]["top10"][10])),
        ]
        rows.append("<tr><td>" + str(i) + "</td>" + "".join(f"<td class='{c}'>{v}</td>" for v, c in cells) + "</tr>")
    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Tinker training log</title><style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; background:#101418; color:#e8edf2; margin:24px; }}
h1 {{ margin:0 0 4px; }} .sub {{ color:#8a96a3; margin-bottom:16px; }}
table {{ border-collapse:collapse; width:100%; margin:10px 0 24px; font-size:13px; }}
th, td {{ padding:6px 8px; border-bottom:1px solid #2a323a; text-align:right; }} th {{ color:#8a96a3; font-weight:600; }}
td:nth-child(2), td:nth-child(3), th:nth-child(2), th:nth-child(3) {{ text-align:left; }}
td.good {{ color:#3ecf73; font-weight:700; }} td.bad {{ color:#ff5a4a; font-weight:700; }}
.chart {{ width:100%; max-width:900px; background:#141a20; border-radius:8px; margin:8px 0 18px; }}
.ct {{ font:700 14px 'Segoe UI'; fill:#e8edf2; }} .ax {{ font:11px 'Segoe UI'; fill:#8a96a3; }} .lg {{ font:700 11px 'Segoe UI'; }}
.grid {{ stroke:#222a32; }}
</style></head><body>
<h1>Tinker training log</h1>
<div class="sub">{len(score)} run(s) on the score sheet, {len(runs)} with a minute-by-minute log. Green = drill target met.</div>
<table><tr><th>#</th><th>Date</th><th>Match</th><th>Keen → first camp<br>(≤ 40 s)</th><th>First ancient<br>(≤ 7:45)</th>
<th>Mana into C<br>(≥ 600)</th><th>Camp trips 5–10<br>(≥ 7)</th><th>Median fountain<br>(≤ 7 s)</th><th>Stops &gt; 8 s<br>(0)</th>
<th>Mana coming home<br>(≥ Immortal 226)</th><th>LH @10<br>(≥ top-10 {DATA['bench_lh']['top10'][10]:.0f})</th><th>NW @10<br>(≥ top-10 {DATA['bench_nw']['top10'][10]:,})</th></tr>
{''.join(rows) or '<tr><td colspan=12>No runs yet: play a game with the coach running.</td></tr>'}</table>
{chart("Net worth per minute", runs, "net_worth", "bench_nw", "gold") if runs else ""}
{chart("Last hits per minute", runs, "lh", "bench_lh", "LH") if runs else ""}
<div class="sub">Runs before net-worth tracking was added only have the score-sheet row. Lobby runs without enemies farm faster than real games; the timing and fountain columns are the ones that carry over.</div>
</body></html>"""
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT}")
    webbrowser.open(OUT.as_uri())


if __name__ == "__main__":
    main()
