"""Tinker jungle-transition drill guide -> PDF."""
import json, math, pathlib, subprocess, statistics as st
from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).parent
T = json.load(open(HERE / "data" / "transition.json"))
M = json.load(open(HERE / "data" / "metrics.json"))
B = json.load(open(HERE / "data" / "drill_bench.json"))
OUT = pathlib.Path(r"C:\Users\docky\Documents\tinker\Tinker_Jungle_Transition_Drills.pdf")
A = HERE / "report_assets"
ME_C, MOD_C, PRO_C = "#e0503c", "#2e9e5b", "#2f8fd0"
fmt = lambda t: "—" if t is None else f"{int(t // 60)}:{int(t % 60):02d}"

# ------------------------------------------------------------------ screenshot cards
FB = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 34)


def card(src, label, color, name):
    im = Image.open(HERE / "shots" / src).convert("RGB").resize((1280, 720), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1280, 52], fill=(0, 0, 0))
    d.rectangle([0, 0, 12, 52], fill=color)
    d.text((26, 6), label, font=FB, fill=(255, 255, 255))
    im.save(A / name, quality=85)
    return name


def pair(a, b, name):
    ia, ib = Image.open(A / a), Image.open(A / b)
    out = Image.new("RGB", (2560 + 16, 720), (255, 255, 255))
    out.paste(ia, (0, 0)); out.paste(ib, (1296, 0))
    out.resize((1288, 360), Image.LANCZOS).save(A / name, quality=88)
    return name


G, R_ = (46, 158, 91), (224, 80, 60)
cards = {
    "R509": card("drill_R_509.png", "MODEL (Radiant) · 5:09 · fountain turnaround, 6.5 s", G, "c_R509.jpg"),
    "R518": card("drill_R_518.png", "MODEL (Radiant) · 5:18 · camp pair next to mid", G, "c_R518.jpg"),
    "R544": card("drill_R_544.png", "MODEL (Radiant) · 5:44 · mid wave, 2 Marches", G, "c_R544.jpg"),
    "R618": card("drill_R_618.png", "MODEL (Radiant) · 6:18 · hard + ancient, lvl 7", G, "c_R618.jpg"),
    "R713": card("drill_R_713.png", "MODEL (Radiant) · 7:13 · ancient again", G, "c_R713.jpg"),
    "R848": card("drill_R_848.png", "MODEL (Radiant) · 8:48 · bot-side camps, Blink in", G, "c_R848.jpg"),
    "D455": card("drill_D_455.png", "MODEL (Dire) · 4:55 · first camp, 18 s after Keen", G, "c_D455.jpg"),
    "D612": card("drill_D_612.png", "MODEL (Dire) · 6:12 · hard camp (Dire side)", G, "c_D612.jpg"),
    "D736": card("drill_D_736.png", "MODEL (Dire) · 7:36 · hard + ancient (Dire side)", G, "c_D736.jpg"),
    "D849": card("drill_D_849.png", "MODEL (Dire) · 8:49 · far camps (mirror of E)", G, "c_D849.jpg"),
    "M540": card("drill_M_540.png", "YOU · 5:40 · fountain after first Keen", R_, "c_M540.jpg"),
    "M547": card("drill_M_547.png", "YOU · 5:47 · back to mid wave", R_, "c_M547.jpg"),
    "M557": card("drill_M_557.png", "YOU · 5:57 · ancient camp with 366 mana → left", R_, "c_M557.jpg"),
    "M645": card("drill_M_645.png", "YOU · 6:45 · 21 s idle in fountain", R_, "c_M645.jpg"),
    "M730": card("drill_M_730.png", "YOU · 7:30 · first camp (finally)", R_, "c_M730.jpg"),
}
pairs = {
    "p1": pair("c_M540.jpg", "c_R509.jpg", "pp1.jpg"),
    "p2": pair("c_M547.jpg", "c_R518.jpg", "pp2.jpg"),
    "p3": pair("c_M557.jpg", "c_R618.jpg", "pp3.jpg"),
    "p4": pair("c_M645.jpg", "c_R713.jpg", "pp4.jpg"),
}

# ------------------------------------------------------------------ station map
LIM = 8300
camps = {c["id"]: c for c in T["camps"]}
STATIONS = [
    ("A", "Mid pair", [1, 2, 3, 7], "#2e9e5b"),
    ("C", "Top-side hard + ancient", [4, 5, 6], "#c0392b"),
    ("D", "Top-lane side", [23, 28, 32, 26], "#8e44ad"),
    ("E", "Bot-south", [19, 21], "#d68910"),
]
BG = []
for g in M:
    team = M[g]["team"]
    for t, x, y, life in M[g]["path"][::8]:
        BG.append((x, y) if team == 2 else (-x, -y))


def station_map(dire=False, S=440):
    f = (lambda x, y: (-x, -y)) if dire else (lambda x, y: (x, y))
    P = lambda x, y: ((f(x, y)[0] + LIM) / (2 * LIM) * S, (LIM - f(x, y)[1]) / (2 * LIM) * S)
    o = [f'<svg viewBox="0 0 {S} {S}" width="{S}" height="{S}" class="map"><rect width="{S}" height="{S}" fill="#101418"/>']
    for x, y in BG[::2]:
        X, Y = P(x, y)
        o.append(f'<rect x="{X:.0f}" y="{Y:.0f}" width="2" height="2" fill="#2c353e"/>')
    fx, fy = P(-6900, -6400)
    o.append(f'<circle cx="{fx:.0f}" cy="{fy:.0f}" r="22" fill="#1f5130"/><text x="{fx:.0f}" y="{fy+4:.0f}" class="ml" text-anchor="middle">F</text>')
    mx, my = P(-1100, -900)
    o.append(f'<circle cx="{mx:.0f}" cy="{my:.0f}" r="15" fill="none" stroke="#f0a93a" stroke-width="3"/><text x="{mx+20:.0f}" y="{my+5:.0f}" class="ml" fill="#f0a93a">B</text>')
    for key, name, ids, col in STATIONS:
        xs = [camps[i]["x"] for i in ids if i in camps]; ys = [camps[i]["y"] for i in ids if i in camps]
        for i in ids:
            if i in camps:
                X, Y = P(camps[i]["x"], camps[i]["y"])
                o.append(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="8" fill="{col}" stroke="#fff" stroke-width="1.2"/>')
        cx, cy = P(st.mean(xs), st.mean(ys))
        o.append(f'<text x="{cx+14:.0f}" y="{cy-10:.0f}" class="ml" fill="{col}">{key}</text>')
    title = "DIRE view (you're top-right)" if dire else "RADIANT view (you're bottom-left)"
    o.append(f'<text x="8" y="18" class="mt">{title}</text></svg>')
    return "".join(o)


# ------------------------------------------------------------------ timelines
def timeline(g, label, color, a=270, b=600, W=820, H=30):
    X = lambda t: 120 + (t - a) / (b - a) * (W - 130)
    o = [f'<svg viewBox="0 0 {W} {H}" class="tl"><text x="0" y="{H/2+4}" class="tll" fill="{color}">{label}</text>']
    steps = T["games"][g]["steps"]
    for i, s in enumerate(steps):
        t0 = max(a, s["t"]); t1 = min(b, s["t"] + s["len"])
        if t1 <= a or t0 >= b: continue
        w = s["where"]
        camps_hit = set(s["camps"])
        if w == "fountain": c = "#b9c1c9"; txt = "F"
        elif camps_hit & {"5", "6", "4"}: c = "#c0392b"; txt = "C"
        elif camps_hit & {"1", "2", "3", "7"}: c = "#2e9e5b"; txt = "A"
        elif camps_hit & {"23", "28", "32", "26"}: c = "#8e44ad"; txt = "D"
        elif camps_hit & {"19", "21", "27"}: c = "#d68910"; txt = "E"
        elif s["lane_kills"]: c = "#f0a93a"; txt = "B" if w == "mid" else "lane"
        else: c = "#e9ecef"; txt = "·"
        o.append(f'<rect x="{X(t0):.1f}" y="4" width="{max(1, X(t1)-X(t0)-1):.1f}" height="{H-8}" fill="{c}" rx="2"/>')
        if X(t1) - X(t0) > 14:
            o.append(f'<text x="{(X(t0)+X(t1))/2:.1f}" y="{H/2+4}" class="tlt" text-anchor="middle">{txt}</text>')
    fk = T["games"][g]["first_keen"]
    o.append(f'<line x1="{X(fk):.1f}" y1="0" x2="{X(fk):.1f}" y2="{H}" stroke="#000" stroke-width="1.5" stroke-dasharray="3 2"/>')
    o.append("</svg>")
    return "".join(o)


def axis(a=270, b=600, W=820):
    X = lambda t: 120 + (t - a) / (b - a) * (W - 130)
    return (f'<svg viewBox="0 0 {W} 16" class="tl">' + "".join(
        f'<text x="{X(t):.0f}" y="12" class="ax" text-anchor="middle">{fmt(t)}</text>' for t in range(300, 601, 60)) + "</svg>")


tls = (axis() + timeline("p9020212922", "Model · Radiant", MOD_C) + timeline("p9020204172", "Model · Dire", MOD_C)
       + timeline("p9020204691", "Immortal #6", MOD_C) + timeline("pro", "Pro", PRO_C) + timeline("me", "You", ME_C))

# ------------------------------------------------------------------ benchmark table
med, res = B["med"], B["res"]
me = res["me"]
best = lambda k, lo=True: (min if lo else max)(res[g][k] for g in B["top"] if res[g][k] is not None)
bench = [
    ("First Keen Teleport", fmt(med["keen"]), fmt(best("keen")), fmt(me["keen"]), "same as the best, not your problem"),
    ("First camp trip (A)", fmt(med["A_t"]), fmt(best("A_t")), fmt(me["A_t"]), "≤ 40 s after Keen"),
    ("First jungle kill", fmt(med["first_neu"]), fmt(best("first_neu")), fmt(me["first_neu"]), "before 6:20"),
    ("First trip to C (hard + ancient)", fmt(med["C_t"]), fmt(best("C_t")), "never before 9:00", "by 6:30–7:30"),
    ("…with mana", f"{med['C_mana']:.0f}", "", "366 (5:55, left)", "≥ 600, straight from fountain"),
    ("First ancient kill", fmt(med["anc"]), fmt(best("anc")), fmt(me["anc"]), "before 7:45"),
    ("Camp trips 5:00–10:00", f"{med['camptrips']:.1f}", f"{best('camptrips', False)}", f"{me['camptrips']}", "7+"),
    ("Mid-wave trips 5:00–10:00", f"{med['waves']:.0f}", "", f"{me['waves']}", "2–3, 2 Marches each"),
    ("Marches per camp trip", f"{med['m_camp']:.1f}", "", f"{me['m_camp']:.1f}", "2 (pair) · 3 (hard + ancient)"),
    ("Fountain stop (median)", f"{med['fstop']:.1f} s", f"{best('fstop'):.1f} s", f"{me['fstop']:.1f} s", "≤ 7 s"),
    ("Neutral gold at 7:00", f"{med['neu7']:.0f}", f"{best('neu7', False)}", f"{me['neu7']}", "≥ 200"),
    ("Neutral gold at 10:00", f"{med['neu10']:.0f}", f"{best('neu10', False)}", f"{me['neu10']}", "≥ 1,200"),
]
bench_rows = "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td><td class='me'>{d}</td><td class='tg'>{e}</td></tr>" for a, b, c, d, e in bench)

html = f"""<!doctype html><html><head><meta charset="utf-8"><title>Tinker Jungle Transition Drills</title><style>
@page {{ size: A4; margin: 12mm 12mm; }}
body {{ font-family:'Segoe UI',Arial,sans-serif; color:#1b1f24; font-size:11.4px; line-height:1.5; margin:0; }}
h1 {{ font-size:30px; margin:0; }} h2 {{ font-size:19px; margin:18px 0 8px; border-bottom:2px solid #1b1f24; padding-bottom:3px; }}
h3 {{ font-size:14px; margin:12px 0 4px; }} .sub {{ color:#5b6570; }} .pb {{ page-break-before:always; }}
.me {{ color:{ME_C}; font-weight:700; }} .tg {{ color:{MOD_C}; font-weight:700; }}
table {{ border-collapse:collapse; width:100%; font-size:10.6px; margin:4px 0 10px; }} th,td {{ border-bottom:1px solid #e3e6ea; padding:4px 6px; text-align:left; }} th {{ background:#f2f4f6; }}
.box {{ background:#f4f6f8; border-radius:6px; padding:10px 14px; margin:8px 0; }}
.rule {{ background:#1b1f24; color:#fff; border-radius:6px; padding:10px 14px; margin:10px 0; font-size:13px; }}
.rule b {{ color:#7fe0a0; }}
.maps {{ display:flex; gap:12px; justify-content:center; }} .map {{ border-radius:6px; }}
.mt {{ fill:#fff; font:700 12.5px 'Segoe UI'; }} .ml {{ fill:#fff; font:800 18px 'Segoe UI'; }}
.tl {{ width:100%; height:auto; display:block; }} .tll {{ font:700 11px 'Segoe UI'; }} .tlt {{ font:700 10px 'Segoe UI'; fill:#1b1f24; }} .ax {{ font:10px 'Segoe UI'; fill:#777; }}
img.shot {{ width:100%; border-radius:5px; display:block; margin:4px 0; }}
.two {{ display:grid; grid-template-columns:1fr 1fr; gap:8px; }} .two img {{ width:100%; border-radius:5px; }}
.phase {{ border-left:5px solid {MOD_C}; padding:2px 0 4px 12px; margin:12px 0; page-break-inside:avoid; }}
.drill {{ border:1.5px solid #d7dce1; border-radius:8px; padding:8px 14px; margin:10px 0; page-break-inside:avoid; }}
.drill h3 {{ margin-top:4px; }} .tag {{ display:inline-block; background:#1b1f24; color:#fff; border-radius:4px; padding:0 6px; font-size:10px; margin-right:6px; }}
.mono {{ font-family:Consolas,monospace; background:#eef1f4; padding:0 4px; border-radius:3px; }}
.key span {{ display:inline-block; margin-right:12px; }} .sw {{ display:inline-block; width:12px; height:12px; border-radius:2px; vertical-align:middle; margin-right:4px; }}
.sheet td {{ height:22px; border:1px solid #c9d0d6; }} .sheet th {{ border:1px solid #c9d0d6; text-align:center; }}
.avoid {{ page-break-inside:avoid; }}
</style></head><body>

<h1>Tinker Jungle Transition: Drill Guide</h1>
<div class="sub">Built from the 10 best laning→jungle transitions in 23 Immortal Tinker games (patch 7.41), plus NothingToSay, compared with your match 9016088490.
All screenshots are from those replays at the exact moments described.</div>

<div class="rule">The whole transition in one sentence: <b>after your first Keen Teleport, every trip is Fountain → Station → Fountain</b>, and the station is a camp pair, not the mid wave, at least 2 out of every 3 trips.</div>

<h2>0 · Targets</h2>
<p>"Top-10 median" is the typical value for the 10 best transitions; "best" is the best single game. Your column is from your match.</p>
<table><tr><th>Checkpoint</th><th>Top-10 median</th><th>Best</th><th>You</th><th>Target</th></tr>{bench_rows}</table>
<p>You got Keen Teleport on time. <b>Everything that goes wrong happens in the first 2 minutes after it.</b> The top 10 were in a camp ~30–40 s after their first Keen; you took almost 2 minutes, and the only jungle attempt in between (the ancient camp at 5:55) was aborted.</p>

<h2>1 · The stations</h2>
<p>Every top transition uses the same small set of destinations. Learn them as letters:</p>
<div class="maps">{station_map(False)}{station_map(True)}</div>
<table>
<tr><th>Station</th><th>What it is</th><th>When the top 10 start using it</th><th>Marches</th></tr>
<tr><td><b>F</b></td><td>Fountain: <span class="mono">b R K</span> and go</td><td>after every station</td><td>0</td></tr>
<tr><td><b style="color:#2e9e5b">A</b></td><td>Camp pair next to mid on your side: medium camp + hard camp just behind it (+ the small camp by the T1)</td><td>first trip after Keen (all 10 used it before 10:00)</td><td>2 (<span class="mono">M R M</span>, Laser the last creep)</td></tr>
<tr><td><b style="color:#f0a93a">B</b></td><td>Mid wave, only when it's in front of your tower / at the rune</td><td>every 2nd–3rd trip</td><td>2 max</td></tr>
<tr><td><b style="color:#c0392b">C</b></td><td>Your side's hard camp + ancient camp (Radiant: top-side of the river; Dire: bottom-side)</td><td>~6:25 at level 7, straight from fountain</td><td>3 (<span class="mono">M R M R M L</span>)</td></tr>
<tr><td><b style="color:#8e44ad">D</b></td><td>Medium + small camps next to your offlane/safelane T2 on the C side</td><td>~7:30 onward</td><td>2</td></tr>
<tr><td><b style="color:#d68910">E</b></td><td>Camps on the far side of your other lane (Radiant: south of bot lane)</td><td>~8:30 onward, usually with Blink</td><td>2</td></tr>
</table>
<p class="sub">Camp creep types rotate between games; the stations don't. Dire uses the same stations mirrored through the middle of the map.</p>

<h2 class="pb">2 · What the transition looks like, trip by trip</h2>
<p>Each bar is one trip between Keen Teleports, 4:30–10:00. The dashed line is the first Keen Teleport.</p>
<p class="key"><span><span class="sw" style="background:#b9c1c9"></span>F fountain</span><span><span class="sw" style="background:#2e9e5b"></span>A mid pair</span><span><span class="sw" style="background:#f0a93a"></span>B wave / lane</span>
<span><span class="sw" style="background:#c0392b"></span>C hard + ancient</span><span><span class="sw" style="background:#8e44ad"></span>D</span><span><span class="sw" style="background:#d68910"></span>E</span><span><span class="sw" style="background:#e9ecef"></span>nothing killed</span></p>
{tls}
<div class="box"><b>Read the model rows:</b> grey and colour strictly alternate: <b>F A F B F C F A F C…</b>. The Dire model went <b>F → A</b> 13 s after his first Keen.
<b>Your row</b>: F → B → a stop at C where no neutral died (shown as “lane”) → F → B → a long grey block (the 21 s idle stop + TP scroll to mid) → F, and the first green block only starts at 7:28.</div>

<h2>3 · The script, phase by phase</h2>

<div class="phase"><h3>Phase 0 · Before Keen (3:30 → Keen)</h3>
<ul><li>Have the mid wave <b>pushed into the enemy tower</b> at the moment Keen comes up, so your first 60 s aren't spent defending a wave.</li>
<li>Know where your first A trip lands before you press the button. Hesitation costs more than a bad route.</li>
<li>The pro also hit camp A from lane with a March before Keen (3 extra kills). Optional, but free.</li></ul></div>

<div class="phase"><h3>Phase 1 · The switch (Keen → +40 s)</h3>
<p><span class="mono">push wave → K to F → b R K → A: M R M (L) → K to F</span></p>
<img class="shot" src="report_assets/c_R509.jpg">
<p>Model at 5:09: lands, one Bottle, Rearm, gone. <b>6.5 s</b>. You can see the Rearm channel bar; nothing else is pressed.</p>
<div class="two"><img src="report_assets/c_R518.jpg"><img src="report_assets/c_D455.jpg"></div>
<p>Model Radiant (5:18) and Model Dire (4:55): first trip goes to <b>A</b>. Robots walking through the camp, Rearm between the two Marches. Both are on their first camp within 20 s of Keen.</p></div>

<div class="phase"><h3>Phase 2 · Alternate A and B (~5:40 → 6:30)</h3>
<p><span class="mono">F → B (M R M) → F → A → F</span>. The wave is a filler between camp trips, not the main event.</p>
<img class="shot" src="report_assets/c_R544.jpg">
<p>Model at 5:44: two Marches on the wave, then home. You used <b>4 Marches on one mid wave at 7:03–7:17</b>; that's a camp's worth of mana.</p></div>

<div class="phase"><h3>Phase 3 · First C trip (~6:15 → 7:40)</h3>
<p><span class="mono">F (full mana) → C: M R M R M L → F</span>. Only enter C <b>straight from fountain with ≥ 600 mana</b>. The top 10 entered with a median of {med['C_mana']:.0f}; nobody went in below ~450.</p>
<div class="two"><img src="report_assets/c_R618.jpg"><img src="report_assets/c_R713.jpg"></div>
<p>Model Radiant at 6:18 (level 7, 868 HP, 42 LH) and again at 7:13: three Marches from the side of the camp so the robots pass through both the hard camp and the ancients. The blue shrine in the corner is the landmark.</p>
<div class="two"><img src="report_assets/c_D612.jpg"><img src="report_assets/c_D736.jpg"></div>
<p>Same station for Dire (mirrored, bottom side). 35 LH at 6:12, 66 LH at 7:36.</p></div>

<div class="phase"><h3>Phase 4 · Widen the loop (~7:30 → 9:00)</h3>
<p>Add <b>D</b> and <b>E</b> as C and A respawn. From Blink onward the trip opens with <span class="mono">B M R M</span>.</p>
<div class="two"><img src="report_assets/c_R848.jpg"><img src="report_assets/c_D849.jpg"></div>
<p>By ~8:50 both models are farming their furthest station while A and C respawn.</p></div>

<h2 class="pb">4 · Your transition next to the model, frame by frame</h2>
<div class="avoid"><h3>① Fountain after the first Keen: 5:40 vs 5:09</h3>
<img class="shot" src="report_assets/pp1.jpg">
<p>Both of you do the right thing here: first Keen goes home. Your stop took 8 s (Bottle ×2 → Rearm → Bottle); his took 6.5 s (Bottle → Rearm → Keen).</p></div>
<div class="avoid"><h3>② Where the first real trip goes: 5:47 vs 5:18</h3>
<img class="shot" src="report_assets/pp2.jpg">
<p><b>This is the moment the game splits.</b> You Keen to the mid wave; he Keens into camp A. Same LH (28 vs 30), but he's now in a loop that pays neutral gold every trip.</p></div>
<div class="avoid"><h3>③ The ancient attempt: 5:57 vs 6:18</h3>
<img class="shot" src="report_assets/pp3.jpg">
<p>You landed at C straight from the mid wave with <b>366 mana at level 6</b>, pressed Rearm and left with nothing. He went to C 20 s later <b>from fountain</b>, level 7, full mana, and cleared hard camp + ancients. Right idea, wrong order: go <b>F → C</b>, never <b>B → C</b>.</p></div>
<div class="avoid"><h3>④ The idle stop: 6:45 vs 7:13</h3>
<img class="shot" src="report_assets/pp4.jpg">
<p>You Keen'd home at 6:32 and <b>pressed nothing for 21 seconds</b> (6:35 → 6:56) with 660+ mana, then used a TP scroll to mid and spent 4 Marches on one wave. In that time the model cleared C a second time. If you're waiting on Keen's cooldown, Rearm resets it; there is never a reason to stand in fountain.</p></div>
<div class="avoid"><h3>⑤ First camp: 7:30</h3>
<img class="shot" src="report_assets/c_M730.jpg">
<p>Your first A trip at 7:28 was good: 13 creeps. It just came ~2 minutes late; the top 10 median first camp trip is {fmt(med['A_t'])}.</p></div>

<h2 class="pb">5 · Drills</h2>
<p>Drills 1–4 use a <b>private lobby with "Enable cheats"</b> (Play → Custom Lobbies → Create; commands are typed in chat: <span class="mono">-lvlup 5</span>, <span class="mono">-gold 3000</span>,
<span class="mono">-item item_bottle</span>, <span class="mono">-refresh</span>, <span class="mono">-startgame</span>, <span class="mono">-spawnneutrals</span>). Pick your usual side, and do both sides once a week.</p>

<div class="drill"><h3><span class="tag">DRILL 1</span>Fountain turnaround</h3>
<p><b>Setup:</b> Tinker level 6 with Bottle. Stand near your T2, Keen home. <b>Rep:</b> land → <span class="mono">b R K</span> to any camp → Keen home again. 20 reps.</p>
<p><b>Pass:</b> every stop ≤ 7 s, and never more than one Bottle press before Rearm. Say "land, bottle, rearm, go" out loud for the first 10.</p></div>

<div class="drill"><h3><span class="tag">DRILL 2</span>The switch</h3>
<p><b>Setup:</b> level 5, <span class="mono">-startgame</span>, farm mid until level 6 at ~5:00 (or <span class="mono">-lvlup</span> when the clock hits 4:45). <b>Rep:</b> the moment Keen is learned: push → K home → <span class="mono">b R K</span> → camp A → <span class="mono">M R M L</span> → K home.</p>
<p><b>Pass:</b> first neutral creep dies ≤ 40 s after Keen is learned. 10 reps.</p></div>

<div class="drill"><h3><span class="tag">DRILL 3</span>March placement</h3>
<p><b>Setup:</b> level 7, <span class="mono">-spawnneutrals</span> to fill the camps. <b>Rep:</b> clear A with exactly 2 Marches (+ Laser), then C with exactly 3 Marches (+ Laser). Cast each March from <b>behind</b> the camp, robots walking through the creeps towards you.</p>
<p><b>Pass:</b> A cleared with 2 Marches, C cleared with 3, 8 out of 10 times. If it takes more, your cast is too far to the side, not "not enough mana".</p></div>

<div class="drill"><h3><span class="tag">DRILL 4</span>The 5-minute loop</h3>
<p><b>Setup:</b> level 6 at 5:00 on the lobby clock, then play 5:00–10:00 alone following <span class="mono">F A F B F C F A F C F D F E</span>, re-spawning neutrals every minute.</p>
<p><b>Pass:</b> 7+ camp trips and ≥ 2 C trips before 10:00; no fountain stop over 8 s; no trip that kills nothing. Record it once and count.</p></div>

<div class="drill"><h3><span class="tag">DRILL 5</span>Mana gate (decision rule)</h3>
<table style="width:90%"><tr><th>Mana when you're about to Keen out</th><th>Go to</th></tr>
<tr><td>≥ 600 (just left fountain)</td><td><b>C</b> (hard + ancient), or A if C isn't up</td></tr>
<tr><td>300–600</td><td><b>A</b> or <b>B</b>, 2 Marches, then home</td></tr>
<tr><td>&lt; 300</td><td>Fountain. Don't Rearm in the jungle.</td></tr></table></div>

<div class="drill"><h3><span class="tag">DRILL 6</span>Live games: 5-game challenge</h3>
<p>For the next 5 Tinker games, only care about <b>5:00–9:00</b>. After each game, open the replay at 2× from the first Keen and fill in the sheet on the next page.</p>
<p><b>Pass:</b> 4 of 5 games with first jungle kill before 6:20 and first ancient before 7:45.</p></div>

<h2 class="pb">6 · Score sheet</h2>
<table class="sheet"><tr><th>Game</th><th>First Keen</th><th>First camp kill</th><th>First C trip (mana)</th><th>First ancient</th><th>Camp trips 5–10</th><th>Stops &gt; 8 s</th><th>Neutral gold @7</th><th>@10</th></tr>
<tr><td>Target</td><td>~5:40</td><td>≤ Keen + 40 s</td><td>≤ 7:30 (≥ 600)</td><td>≤ 7:45</td><td>7+</td><td>0</td><td>≥ 200</td><td>≥ 1,200</td></tr>
<tr><td class="me">Now</td><td>{fmt(me['keen'])}</td><td>{fmt(me['first_neu'])}</td><td>—</td><td>{fmt(me['anc'])}</td><td>{me['camptrips']}</td><td>many</td><td>{me['neu7']}</td><td>{me['neu10']}</td></tr>
{''.join(f'<tr><td>{i}</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>' for i in range(1, 6))}
</table>
<div class="box"><b>Where to read these in the replay:</b> neutral gold is in the scoreboard's gold breakdown (or the post-game graphs); "first ancient" is when your LH jumps by 3+ while you're at C.
If you send me the match IDs, I'll run the same parser on them and fill the sheet for you.</div>

<h3>Why these targets</h3>
<ul>
<li>Across all 24 reference games, an earlier first jungle kill and an earlier first ancient both go with more net worth at 15:00 (r ≈ −0.4 each), and shorter fountain stops go with more (r ≈ −0.5).</li>
<li>Your lane, your Keen timing and your Blink timing are already at or above the Immortal median. The transition is the one part of your early game that's clearly below it.</li>
</ul>

<h2>Appendix · The 10 model transitions (5:00–8:00)</h2>
<p class="sub">Station order per trip. F = fountain, A/C/D/E = stations above, B = mid wave, lane = side lane.</p>
<table><tr><th>Game</th><th>Side</th><th>Keen</th><th>1st camp</th><th>1st ancient</th><th>Neutral @10</th><th>Route</th></tr>
{''.join(f"<tr><td>{g}</td><td>{'Radiant' if T['games'][g]['team']==2 else 'Dire'}</td><td>{fmt(res[g]['keen'])}</td><td>{fmt(res[g]['first_neu'])}</td><td>{fmt(res[g]['anc'])}</td><td>{res[g]['neu10']:,}</td><td class='mono' style='font-size:9.5px'>" + ' '.join(('F' if s['where']=='fountain' else 'C' if set(s['camps'])&{'4','5','6'} else 'A' if set(s['camps'])&{'1','2','3','7'} else 'D' if set(s['camps'])&{'23','28','32','26'} else 'E' if set(s['camps'])&{'19','21','27'} else 'B' if s['lane_kills'] else '·') for s in T['games'][g]['steps'] if 290 <= s['t'] < 480) + "</td></tr>" for g in B['top'])}
<tr style="background:#fdecea"><td>You</td><td>Radiant</td><td>{fmt(me['keen'])}</td><td>{fmt(me['first_neu'])}</td><td>{fmt(me['anc'])}</td><td>{me['neu10']}</td><td class='mono' style='font-size:9.5px'>{' '.join(('F' if s['where']=='fountain' else 'C' if set(s['camps'])&{'4','5','6'} else 'A' if set(s['camps'])&{'1','2','3','7'} else 'B' if s['lane_kills'] else '·') for s in T['games']['me']['steps'] if 290 <= s['t'] < 480)}</td></tr>
</table>
</body></html>"""

(HERE / "drill.html").write_text(html, encoding="utf-8")
chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={OUT}",
                (HERE / "drill.html").as_uri()], check=True, capture_output=True, timeout=180)
print(OUT, OUT.stat().st_size)
