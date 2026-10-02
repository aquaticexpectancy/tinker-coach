"""Live bot-batch dashboard (same numbers as lab_hud.py --batch and the Telegram message), as a web page.

    python batch_web.py            # http://localhost:8765, refreshes every 3 s
"""
import json
import math
import statistics as st
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import lab_hud

try:
    import bot_batch
    SETUPS = bot_batch.SETUPS
except Exception:
    SETUPS = {}

NOTES = {
    "lab_10x": "control: the bot's current lab plan",
    "wave3_10x": "3 Marches at the mid wave, rest as lab",
    "combo_10x": "wave 3 + 2 Marches at D + leave fountain at 360 mana + A,B,D,B,C,B cycle",
    "sweep1_10x": "combo + Keen mid just before the waves meet, 1 March, leave at once",
    "sweep2_10x": "combo + Keen mid just before the waves meet, 2 Marches, leave at once",
}
PRED = {"wave3_10x": 173, "combo_10x": 334}      # simulator: gain over lab_10x (sim/SEARCH2.md)
H = lab_hud.BatchHud(lab_hud.latest_batch(), 5, window=False)


def stats(v):
    n = len(v)
    m = sum(v) / n if n else None
    sd = st.stdev(v) if n > 1 else 0.0
    return n, m, sd, (sd / math.sqrt(n) if n else 0.0)


def data():
    H.read()
    now = time.time()
    order, rows = H.order, H.rows
    total, done = len(order), len(rows)
    setups = list(dict.fromkeys(order)) or list(dict.fromkeys(r["setup"] for r in rows))
    ended = bool(H.status.get("done")) or bool(total and done >= total) or bool(H.status.get("stopped"))
    frac = 0.0
    clock = H.game_clock
    if not ended and clock is not None and clock >= lab_hud.DRILL_FROM - 5:
        frac = min(1.0, max(0.0, (clock - lab_hud.DRILL_FROM) / (lab_hud.DRILL_TO - lab_hud.DRILL_FROM)))
    progress = done + frac
    elapsed = now - (H.start or now)
    eta = elapsed / progress * (total - progress) if progress > 0.2 and total and not ended else None
    per = elapsed / progress if progress > 0.2 else None
    base = setups[0] if setups else None
    ok = {s: [r for r in rows if r["setup"] == s and r["status"] == "ok"] for s in setups}
    bn, bm, bsd, bse = stats([float(r["nw"]) for r in ok.get(base, [])])
    cards = []
    for s in setups:
        v = ok[s]
        n, m, sd, se = stats([float(r["nw"]) for r in v])
        diff = ci = None
        if s != base and m is not None and bm is not None:
            diff, ci = m - bm, 1.96 * math.hypot(se, bse)
        f = lambda k: sum(float(r[k]) for r in v) / n if n else None
        cards.append({"setup": s, "note": NOTES.get(s, ""), "flags": " ".join(SETUPS.get(s, [])), "n": n,
                      "mean": m, "sd": sd, "se": se, "diff": diff, "ci": ci, "pred": PRED.get(s),
                      "lh": f("lh"), "camp_lh": f("camp_lh"), "wave_lh": f("wave_lh"),
                      "camp_trips": f("camp_trips"), "wave_trips": f("wave_trips"),
                      "nws": [float(r["nw"]) for r in v]})
    # running gain over the control, after each full round
    trend = {}
    for s in setups[1:]:
        pts = []
        for k in range(1, max(len(ok[s]), 1) + 1):
            a = [float(r["nw"]) for r in ok[s][:k]]
            b = [float(r["nw"]) for r in ok[base][:k]]
            if len(a) == k and len(b) == k:
                pts.append(sum(a) / k - sum(b) / k)
        trend[s] = pts
    queue = []
    for i, s in enumerate(order):
        item = {"i": i + 1, "setup": s}
        if i < done:
            item.update(state="done", nw=float(rows[i]["nw"]), ok=rows[i]["status"] == "ok")
        elif i == done and not ended:
            item.update(state="running")
        else:
            item.update(state="queued")
            if per:
                item["at"] = time.strftime("%H:%M", time.localtime(now + (i - progress) * per))
        queue.append(item)
    fails = sum(1 for r in rows if r["status"] != "ok")
    if H.status.get("stopped"):
        state = "stopped"
    elif ended:
        state = "done"
    elif H.game_wall and (clock or -1) >= 0 and now - H.game_wall > 60:
        state = "stalled"
    else:
        state = "running"
    return {"csv": H.base, "state": state, "fails": fails, "total": total, "done": done, "progress": progress,
            "clock": clock, "nw": H.game_nw, "speed": H.game_speed, "cur": order[done] if done < total else None,
            "from": lab_hud.DRILL_FROM, "to": lab_hud.DRILL_TO, "elapsed": elapsed, "eta": eta,
            "done_at": time.strftime("%H:%M", time.localtime(now + eta)) if eta else None,
            "base": base, "cards": cards, "trend": trend, "queue": queue,
            "games": [{"i": i + 1, "setup": r["setup"], "nw": float(r["nw"]), "lh": float(r["lh"]),
                       "camp_lh": float(r["camp_lh"]), "wave_lh": float(r["wave_lh"]), "ok": r["status"] == "ok"}
                      for i, r in enumerate(rows)][-14:][::-1]}


PAGE = r"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Tinker batch</title><style>
:root{--bg:#0d0f14;--card:#161a22;--line:#262c38;--tx:#e8ebf2;--mu:#8b93a7;--g:#3ddc97;--r:#ff6b6b;--y:#ffc857;--b:#6aa9ff;--p:#b48cff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:14px/1.45 system-ui,sans-serif;padding:20px;max-width:1100px;margin:auto}
h1{margin:0 0 4px;font-size:22px}h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--mu);margin:26px 0 10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}
.row{display:flex;gap:12px;flex-wrap:wrap}.row>*{flex:1 1 220px}.mu{color:var(--mu)}.big{font-size:30px;font-weight:700}
.pill{display:inline-block;padding:2px 10px;border-radius:99px;font-size:12px;font-weight:600}
.running{background:#12382a;color:var(--g)}.done{background:#1b2c4a;color:var(--b)}.stalled,.stopped{background:#431d1d;color:var(--r)}
.bar{height:10px;background:#252b38;border-radius:6px;overflow:hidden;margin:8px 0}.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--b),var(--g));transition:width .8s}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip{padding:5px 9px;border-radius:9px;font-size:12px;border:1px solid var(--line);background:#12151c}
.chip.done{background:#10261d;border-color:#1f5a40;color:var(--tx)}.chip.running{border-color:var(--y);color:var(--y);animation:p 1.2s infinite}
.chip.queued{color:var(--mu)}@keyframes p{50%{box-shadow:0 0 0 4px #ffc85733}}
.pos{color:var(--g)}.neg{color:var(--r)}table{width:100%;border-collapse:collapse}td,th{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right}
th{color:var(--mu);font-weight:500;font-size:12px}td:first-child,th:first-child{text-align:left}code{font-size:11px;color:var(--mu);word-break:break-all}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px}svg{width:100%;height:auto;display:block}
</style></head><body><div id=app>loading…</div><script>
const C=['#6aa9ff','#3ddc97','#b48cff','#ffc857'],f0=x=>x==null?'–':Math.round(x).toLocaleString(),mm=s=>{s=Math.max(0,Math.round(s));return Math.floor(s/60)+':'+String(s%60).padStart(2,'0')},sg=x=>(x>=0?'+':'')+Math.round(x);
function strip(cards){const W=1000,H=60+cards.length*46,all=cards.flatMap(c=>c.nws);if(!all.length)return'';const lo=Math.min(...all)-100,hi=Math.max(...all)+100,X=v=>60+(v-lo)/(hi-lo)*(W-90);let s=`<svg viewBox="0 0 ${W} ${H}">`;
for(let t=Math.ceil(lo/200)*200;t<=hi;t+=200)s+=`<line x1=${X(t)} x2=${X(t)} y1=10 y2=${H-30} stroke="#262c38"/><text x=${X(t)} y=${H-10} fill="#8b93a7" font-size=14 text-anchor=middle>${t}</text>`;
cards.forEach((c,i)=>{const y=34+i*46;s+=`<text x=0 y=${y+5} fill="#8b93a7" font-size=13>${c.setup.replace('_10x','')}</text>`;c.nws.forEach((v,j)=>s+=`<circle cx=${X(v)} cy=${y+((j%3)-1)*6} r=5 fill="${C[i%4]}" opacity="0.55"/>`);
if(c.mean!=null)s+=`<line x1=${X(c.mean)} x2=${X(c.mean)} y1=${y-16} y2=${y+16} stroke="${C[i%4]}" stroke-width="3"/><rect x=${X(c.mean-1.96*c.se)} y=${y+19} width=${X(c.mean+1.96*c.se)-X(c.mean-1.96*c.se)} height=4 fill="${C[i%4]}" opacity=.6 />`});return s+'</svg>'}
function trend(d){const ks=Object.keys(d.trend).filter(k=>d.trend[k].length);if(!ks.length)return'<span class=mu>needs a few finished rounds</span>';const all=ks.flatMap(k=>d.trend[k]).concat([0]),lo=Math.min(...all)-40,hi=Math.max(...all)+40,W=1000,H=220,n=Math.max(...ks.map(k=>d.trend[k].length)),X=i=>50+i/Math.max(n-1,1)*(W-80),Y=v=>H-30-(v-lo)/(hi-lo)*(H-50);
let s=`<svg viewBox="0 0 ${W} ${H}"><line x1=50 x2=${W-30} y1=${Y(0)} y2=${Y(0)} stroke="#555" stroke-dasharray="4"/>`;
ks.forEach((k,i)=>{const p=d.trend[k];s+=`<polyline fill=none stroke="${C[(i+1)%4]}" stroke-width=3 points="${p.map((v,j)=>X(j)+','+Y(v)).join(' ')}"/>`;
const pr=d.cards.find(c=>c.setup==k).pred;if(pr!=null)s+=`<line x1=50 x2=${W-30} y1=${Y(pr)} y2=${Y(pr)} stroke="${C[(i+1)%4]}" stroke-dasharray="2 6" opacity=.7 /><text x=${W-30} y=${Y(pr)-5} fill="${C[(i+1)%4]}" font-size=12 text-anchor=end>sim predicted ${sg(pr)}</text>`;
s+=`<text x=${X(p.length-1)+6} y=${Y(p[p.length-1])+4} fill="${C[(i+1)%4]}" font-size=14>${k.replace('_10x','')} ${sg(p[p.length-1])}</text>`});return s+'</svg>'}
async function tick(){let d;try{d=await (await fetch('data.json')).json()}catch(e){return}
const pct=d.total?100*d.progress/d.total:0,play=d.clock!=null&&d.clock>=d.from-5,gp=play?Math.min(100,Math.max(0,100*(d.clock-d.from)/(d.to-d.from))):0;
let h=`<h1>Tinker bot batch <span class="pill ${d.state}">${d.state}${d.fails?' · '+d.fails+' failed':''}</span></h1><div class=mu>${d.csv} · ${d.base} is the control</div>
<h2>Progress</h2><div class=row><div class=card><div class=mu>games</div><div class=big>${d.done}<span class=mu> / ${d.total}</span></div><div class=bar><i style="width:${pct}%"></i></div><span class=mu>${pct.toFixed(0)}%</span></div>
<div class=card><div class=mu>playing now</div><div class=big>${d.cur?d.cur.replace('_10x',''):'–'}</div><div class=bar><i style="width:${gp}%"></i></div><span class=mu>${d.clock==null?'Dota loading':play?mm(d.clock)+' / '+mm(d.to)+(d.nw!=null?' · nw '+f0(d.nw):''):'to 5:00 '+mm(d.clock)}${d.speed?' · '+d.speed+'x':''}</span></div>
<div class=card><div class=mu>time</div><div class=big>${d.eta?mm(d.eta):'–'}<span class=mu> left</span></div><span class=mu>elapsed ${mm(d.elapsed)} · done ≈ ${d.done_at||'–'}</span></div></div>
<h2>Results: net worth at 10:00</h2><div class=row>`;
d.cards.forEach((c,i)=>{h+=`<div class=card><div><span class=dot style="background:${C[i%4]}"></span><b>${c.setup}</b></div><div class=mu style="min-height:34px">${c.note}</div><div class=big>${f0(c.mean)}</div>
<div class=mu>${c.n} games · sd ${f0(c.sd)} · ±${f0(1.96*c.se)} (95%)</div>${c.diff!=null?`<div class="${c.diff>=0?'pos':'neg'}" style="font-size:20px;font-weight:700">${sg(c.diff)} <span class=mu style="font-size:12px;font-weight:400">±${Math.round(c.ci)} vs control${c.pred!=null?' · simulator said '+sg(c.pred):''}</span></div>`:''}
<div class=mu>last hits ${c.lh==null?'–':c.lh.toFixed(1)} · camp ${c.camp_lh==null?'–':c.camp_lh.toFixed(2)}/trip · wave ${c.wave_lh==null?'–':c.wave_lh.toFixed(2)}/trip</div></div>`});
h+=`</div><h2>Every game (dot) · mean (bar) · 95% range</h2><div class=card>${strip(d.cards)}</div>
<h2>Gain over the control as games come in</h2><div class=card>${trend(d)}</div>
<h2>Schedule</h2><div class=card><div class=chips>${d.queue.map(q=>`<span class="chip ${q.state}">${q.i}. ${q.setup.replace('_10x','')}${q.state=='done'?' '+f0(q.nw):q.state=='queued'&&q.at?' · '+q.at:''}${q.state=='running'?' ▶':''}</span>`).join('')}</div></div>
<h2>What each setup runs</h2><div class=card>${d.cards.map((c,i)=>`<div style="margin:6px 0"><span class=dot style="background:${C[i%4]}"></span><b>${c.setup}</b><br><code>${c.flags||'–'}</code></div>`).join('')}</div>
<h2>Latest finished games</h2><div class=card><table><tr><th>#<th>setup<th>net worth<th>last hits<th>camp/trip<th>wave/trip</tr>${d.games.map(g=>`<tr><td>${g.i}<td>${g.setup.replace('_10x','')}<td>${g.ok?f0(g.nw):'failed'}<td>${g.lh}<td>${g.camp_lh.toFixed(2)}<td>${g.wave_lh.toFixed(2)}</tr>`).join('')}</table></div>
<p class=mu>Net worth includes the start state. Gains need about 60+ to be real at 16 games a setup. Refreshes every 3 s.</p>`;
document.getElementById('app').innerHTML=h}tick();setInterval(tick,3000)</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path.startswith("/data.json"):
                body, ctype = json.dumps(data()).encode(), "application/json"
            else:
                body, ctype = PAGE.encode(), "text/html; charset=utf-8"
            self.send_response(200)
        except Exception as e:
            body, ctype = f"error: {e}".encode(), "text/plain"
            self.send_response(500)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("http://localhost:8765")
    HTTPServer(("127.0.0.1", 8765), Handler).serve_forever()
