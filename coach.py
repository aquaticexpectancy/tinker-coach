"""Tinker Coach: live tips from Dota 2 Game State Integration.

    python coach.py              start the coach (transparent HUD + minimap ring; listens on 127.0.0.1:3031)
                                 Ctrl+Alt+P full panel · Ctrl+Alt+U move overlays · Ctrl+Alt+H hide · Ctrl+Alt+Q quit
    python coach.py --install    write Dota's GSI config file (once)
    python coach.py --no-record  don't save the session (default: sessions/<date_time>.jsonl)

Dota must be started with the launch option  -gamestateintegration
"""
from __future__ import annotations

import argparse
import csv
import http.server
import json
import pathlib
import queue
import sys
import threading
import time
import tkinter as tk

import drill
import mapart
import overlays
from engine import DATA, STATION_NAMES, Engine, fmt

HERE = pathlib.Path(__file__).parent
PORT = 3031
TOKEN = "tinkercoach"
CFG_NAME = "gamestate_integration_tinkercoach.cfg"
SCORESHEET = HERE / "scoresheet.csv"


def append_row(path, row: dict):
    """Append to a CSV, upgrading its header if this row brings new columns (old rows keep their values)."""
    rows, fields = [], list(row)
    if path.exists():
        with open(path, encoding="utf-8", newline="") as fh:
            rd = csv.reader(fh)
            header = next(rd, [])
            for r in rd:
                d = dict(zip(header, r))
                extra = r[len(header):]                        # rows written before the header learned new columns
                for k, v in zip([f for f in fields if f not in header], extra):
                    d[k] = v
                rows.append(d)
        fields = header + [f for f in fields if f not in header]
    rows.append(row)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
RUNS = HERE / "runs.csv"          # one row per game minute of every run (see stats.py)
RUN_FIELDS = ["session", "match", "hero", "team", "minute", "lh", "net_worth", "nw_vs_immortal", "gold", "gpm", "xpm",
              "level", "camp_trips", "fountain_stops", "stops_over_8s", "items"]

BG, PANEL, FG, DIM = "#101418", "#1a2027", "#e8edf2", "#8a96a3"
COL = {"good": "#3ecf73", "warn": "#f0b43a", "bad": "#ff5a4a", "info": "#7fb8ff"}
ST_COL = {"F": "#9aa4ad", "A": "#2e9e5b", "B": "#f0a93a", "C": "#d9443a", "D": "#9b59b6", "E": "#e08e1b",
          "lane": "#c9a227", "jungle": "#55606b", "enemy": "#ff2d55", "?": "#55606b"}


# ---------------------------------------------------------------------- install
def dota_cfg_dir() -> pathlib.Path | None:
    for base in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam", r"D:\Steam", r"D:\SteamLibrary"):
        p = pathlib.Path(base) / "steamapps" / "common" / "dota 2 beta" / "game" / "dota" / "cfg"
        if p.exists():
            return p
    return None


def install():
    cfg = dota_cfg_dir()
    if not cfg:
        print("Couldn't find Dota's cfg folder. Copy the block below into\n"
              "  <steam>/steamapps/common/dota 2 beta/game/dota/cfg/gamestate_integration/" + CFG_NAME)
    text = f'''"Tinker Coach"
{{
    "uri"        "http://127.0.0.1:{PORT}/"
    "timeout"    "30.0"
    "buffer"     "0.05"
    "throttle"   "0.05"
    "heartbeat"  "2.0"
    "data"
    {{
        "provider"   "1"
        "map"        "1"
        "player"     "1"
        "hero"       "1"
        "abilities"  "1"
        "items"      "1"
        "minimap"    "1"
    }}
    "auth"
    {{
        "token"      "{TOKEN}"
    }}
}}
'''
    if cfg:
        try:
            for pth in mapart.extract(cfg.parent):
                print(f"Extracted map art -> {pth.name}")
            print(f"Extracted item prices -> {mapart.extract_item_costs(cfg.parent).name}")
            print(f"Extracted neutral creep stats -> {mapart.extract_neutral_stats(cfg.parent).name}")
            print(drill.install())
            print(f"Extracted {len(mapart.extract_icons(cfg.parent))} ability icons -> icons/")
        except Exception as ex:  # Pillow missing or VPK layout changed
            print(f"Map art not extracted ({ex}); the coach still works without it.")
        d = cfg / "gamestate_integration"
        d.mkdir(exist_ok=True)
        (d / CFG_NAME).write_text(text, encoding="utf-8")
        print(f"Wrote {d / CFG_NAME}")
    else:
        print(text)
    print("\nNow add  -gamestateintegration  to Dota's launch options in Steam\n"
          "(Library > Dota 2 > Properties > General > Launch Options) and restart Dota.")


# ---------------------------------------------------------------------- server
SESSIONS = HERE / "sessions"
SESSION_ID = time.strftime("%Y-%m-%d_%H%M")
KEEP_KEYS = ("map", "player", "hero", "abilities", "items")   # the minimap block is big and not needed for review


def start_server(q: queue.Queue, record_path: pathlib.Path | None):
    rec = open(record_path, "a", encoding="utf-8") if record_path else None
    last_rec = [0.0]

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(n)
            self.send_response(200)
            self.end_headers()           # answer first: Dota keeps one request in flight
            try:
                p = json.loads(body)
            except ValueError:
                return
            if (p.get("auth") or {}).get("token") not in (TOKEN, None):
                return
            q.put((time.time(), p))
            if rec and time.time() - last_rec[0] >= 0.25:      # 4 per second is plenty for review
                last_rec[0] = time.time()
                slim = {k: p[k] for k in KEEP_KEYS if k in p}
                rec.write(json.dumps({"t": time.time(), "p": slim}) + "\n")
                rec.flush()

        def log_message(self, *a):
            pass

    class Server(http.server.ThreadingHTTPServer):
        # Python's HTTPServer sets SO_REUSEADDR, which on Windows lets a second coach bind the
        # same port and both draw overlays. Exclusive use makes the second one fail instead.
        allow_reuse_address = False

        def server_bind(self):
            import socket
            if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            super().server_bind()

    srv = Server(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ---------------------------------------------------------------------- UI
class App:
    MAP = 300

    def __init__(self, root: tk.Tk, q: queue.Queue):
        self.root, self.q = root, q
        self.eng = Engine()
        root.title("Tinker Coach")
        root.configure(bg=BG)
        root.attributes("-topmost", True)
        root.geometry("850x690+20+60")
        f = lambda s, w="bold": ("Segoe UI", s, w)
        self.f = f

        # ---- header across the top
        top = tk.Frame(root, bg=BG); top.pack(fill="x", padx=12, pady=(8, 2))
        self.clock_l = tk.Label(top, text="--:--", font=f(24), fg=FG, bg=BG); self.clock_l.pack(side="left")
        self.lvl_l = tk.Label(top, text="", font=f(12), fg=FG, bg=BG); self.lvl_l.pack(side="left", padx=12)
        self.lh_l = tk.Label(top, text="", font=f(11, "normal"), fg=DIM, bg=BG); self.lh_l.pack(side="left", padx=8)
        self.status_l = tk.Label(top, text="● waiting for Dota", font=f(9, "normal"), fg=DIM, bg=BG); self.status_l.pack(side="right")
        self.mana_c = tk.Canvas(root, height=18, bg=PANEL, highlightthickness=0); self.mana_c.pack(fill="x", padx=12, pady=(2, 6))

        body = tk.Frame(root, bg=BG); body.pack(fill="both", expand=True, padx=12)
        left = tk.Frame(body, bg=BG, width=500); left.pack(side="left", fill="both", expand=True)
        right = tk.Frame(body, bg=BG); right.pack(side="left", fill="y", padx=(12, 0))

        # ---- LEFT: next station
        nx = tk.Frame(left, bg=PANEL); nx.pack(fill="x")
        tk.Label(nx, text="NEXT STATION", font=f(9), fg=DIM, bg=PANEL).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 0))
        self.rec_l = tk.Label(nx, text="?", font=f(44), fg=FG, bg=PANEL, width=2); self.rec_l.grid(row=1, column=0, rowspan=2, padx=6)
        self.recname_l = tk.Label(nx, text="", font=f(16), fg=FG, bg=PANEL, anchor="w"); self.recname_l.grid(row=1, column=1, sticky="sw")
        self.why_l = tk.Label(nx, text="", font=f(10, "normal"), fg=DIM, bg=PANEL, anchor="w", wraplength=380, justify="left")
        self.why_l.grid(row=2, column=1, sticky="nw", pady=(0, 8))

        # ---- LEFT: the guide ("do this now")
        gd = tk.Frame(left, bg="#141a20", highlightthickness=2, highlightbackground="#2e9e5b"); gd.pack(fill="x", pady=8)
        self.guide_title = tk.Label(gd, text="DO THIS NOW", font=f(11), fg="#7fe0a0", bg="#141a20", anchor="w")
        self.guide_title.pack(fill="x", padx=10, pady=(6, 2))
        self.guide_ls = []
        for _ in range(7):
            l = tk.Label(gd, text="", font=f(13, "normal"), fg=DIM, bg="#141a20", anchor="w")
            l.pack(fill="x", padx=12)
            self.guide_ls.append(l)
        tk.Frame(gd, height=6, bg="#141a20").pack()

        # ---- LEFT: timer + warnings (fixed height so nothing jumps)
        self.stop_l = tk.Label(left, text="", font=("Consolas", 26, "bold"), fg=FG, bg=BG, anchor="w"); self.stop_l.pack(fill="x")
        self.tips_f = tk.Frame(left, bg=BG, height=96); self.tips_f.pack(fill="x"); self.tips_f.pack_propagate(False)
        self.tip_ls = [tk.Label(self.tips_f, text="", font=f(12), fg=FG, bg=BG, anchor="w", wraplength=480, justify="left") for _ in range(3)]
        for l in self.tip_ls:
            l.pack(fill="x")

        # ---- RIGHT: official map + trips + checklist
        self.map_c = tk.Canvas(right, width=self.MAP, height=self.MAP, bg="#0b0f13", highlightthickness=0); self.map_c.pack()
        self.map_imgs = {}
        for key, name in (("simple", "map_simple.png"), ("detailed", "map_detailed.png")):
            p = HERE / name
            if p.exists():
                self.map_imgs[key] = tk.PhotoImage(file=str(p))
        self.map_style = tk.StringVar(value="simple")
        tk.Label(right, text="TRIPS  (F fountain · A/C/D/E camps · B wave)", font=f(8), fg=DIM, bg=BG, anchor="w").pack(fill="x", pady=(6, 0))
        self.trips_c = tk.Canvas(right, width=self.MAP, height=96, bg=BG, highlightthickness=0); self.trips_c.pack()
        tk.Label(right, text="CHECKLIST 5:00–10:00", font=f(8), fg=DIM, bg=BG, anchor="w").pack(fill="x")
        self.chk_f = tk.Frame(right, bg=BG); self.chk_f.pack(fill="x")
        self.chk = []
        for i in range(6):
            a = tk.Label(self.chk_f, text="", font=f(10), fg=FG, bg=BG, width=2); a.grid(row=i, column=0)
            b = tk.Label(self.chk_f, text="", font=f(9, "normal"), fg=FG, bg=BG, anchor="w"); b.grid(row=i, column=1, sticky="w")
            c = tk.Label(self.chk_f, text="", font=f(9, "normal"), fg=DIM, bg=BG, anchor="e"); c.grid(row=i, column=2, sticky="e", padx=4)
            self.chk.append((a, b, c))
        self.chk_f.columnconfigure(1, weight=1)

        # ---- footer
        bot = tk.Frame(root, bg=BG); bot.pack(fill="x", side="bottom", padx=12, pady=6)
        opt = dict(fg=FG, bg=BG, selectcolor=PANEL, activebackground=BG, activeforeground=FG)
        self.top_v = tk.BooleanVar(value=True)
        tk.Checkbutton(bot, text="on top", variable=self.top_v, command=lambda: root.attributes("-topmost", self.top_v.get()), **opt).pack(side="left")
        for val, txt in (("simple", "simple map"), ("detailed", "detailed map")):
            tk.Radiobutton(bot, text=txt, value=val, variable=self.map_style, command=self._draw_map_base, **opt).pack(side="left")
        tk.Label(bot, text=f"GSI 127.0.0.1:{PORT}", font=f(8, "normal"), fg=DIM, bg=BG).pack(side="right")
        self._draw_map_base()
        self.listeners = []
        self.root.after(100, self.tick)

    # world -> canvas, same mapping as resource/overviews/dota.txt (real orientation)
    def _xy(self, x, y):
        span = mapart.WORLD_MAX - mapart.WORLD_MIN
        return (x - mapart.WORLD_MIN) / span * self.MAP, (mapart.WORLD_MAX - y) / span * self.MAP

    def _real(self, x, y):
        return (x, y) if self.eng.team == "radiant" else (-x, -y)

    def _draw_map_base(self):
        c = self.map_c
        c.delete("base")
        img = self.map_imgs.get(self.map_style.get()) or next(iter(self.map_imgs.values()), None)
        if img:
            c.create_image(0, 0, image=img, anchor="nw", tags="base")
        else:
            c.create_text(self.MAP / 2, 14, text="run: python coach.py --install", fill=DIM, tags="base")
        for st, camps in DATA["stations"].items():
            for cp in camps:
                X, Y = self._xy(*self._real(cp["x"], cp["y"]))
                c.create_oval(X - 6, Y - 6, X + 6, Y + 6, fill=ST_COL[st], outline="#000", width=1, tags="base")
            X, Y = self._xy(*self._real(sum(p["x"] for p in camps) / len(camps), sum(p["y"] for p in camps) / len(camps)))
            c.create_text(X + 15, Y - 12, text=st, fill="#000", font=("Segoe UI", 15, "bold"), tags="base")
            c.create_text(X + 14, Y - 13, text=st, fill=ST_COL[st], font=("Segoe UI", 15, "bold"), tags="base")
        self._map_team = self.eng.team

    def tick(self):
        n = 0
        while not self.q.empty() and n < 200:
            wall, p = self.q.get()
            self.eng.update(p, wall)
            n += 1
        self.eng.speech_queue.clear()          # no voice: callouts only show on screen
        if self.eng.team != getattr(self, "_map_team", None):
            self._draw_map_base()
        if self.root.state() != "withdrawn":
            self.render()
        for fn in self.listeners:
            fn()
        self._maybe_summary()
        self.root.after(100, self.tick)

    def render(self):
        e, v = self.eng, self.eng.view()
        age = time.time() - e.last_payload_wall if e.last_payload_wall else None
        if age is None:
            self.status_l.config(text="● waiting for Dota", fg=DIM)
        elif age < 5:
            self.status_l.config(text="● live", fg=COL["good"])
        else:
            self.status_l.config(text=f"● no data {int(age)} s", fg=COL["warn"])
        self.clock_l.config(text=fmt(v["clock"]) if v["clock"] is not None else "--:--")
        self.lvl_l.config(text=f"lvl {v['level']}" if v["level"] else "")
        mc = self.mana_c; mc.delete("all"); w = mc.winfo_width() or 820
        frac = max(0, min(1, v["mana"] / v["max_mana"])) if v["max_mana"] else 0
        mc.create_rectangle(0, 0, w * frac, 18, fill="#2f6fd0" if v["mana"] >= 300 else "#b33", outline="")
        mc.create_text(8, 9, text=f"{int(v['mana'])} / {int(v['max_mana'])} mana", anchor="w", fill=FG, font=("Segoe UI", 9, "bold"))
        imm, top = v["bench"]
        d = v["lh"] - imm
        txt = f"LH {v['lh']} ({d:+.0f} vs Immortal, {v['lh'] - top:+.0f} vs top-10)"
        if v["net_worth"] is not None:
            nimm, ntop = e.bench_nw()
            txt += f"  ·  NW {v['net_worth']:,} ({v['net_worth'] - nimm:+,} / {v['net_worth'] - ntop:+,})"
        self.lh_l.config(text=txt, fg=COL["good"] if d >= 0 else COL["warn"])
        rec = v["rec"]
        self.rec_l.config(text=rec, fg=ST_COL.get(rec, FG))
        self.recname_l.config(text=STATION_NAMES.get(rec, rec), fg=ST_COL.get(rec, FG))
        self.why_l.config(text=v["why"])
        # guide
        g = v["guide"]
        self.guide_title.config(text="DO THIS NOW  ·  " + g["title"])
        for i, l in enumerate(self.guide_ls):
            if i < len(g["steps"]):
                s = g["steps"][i]
                if i < g["cur"]:
                    l.config(text=f"  ✓  {s}", fg="#4d5a66", font=self.f(12, "normal"))
                elif i == g["cur"]:
                    l.config(text=f"  ▶  {s}", fg="#ffffff", font=self.f(16))
                else:
                    l.config(text=f"  {i + 1}.  {s}", fg="#a9b4bf", font=self.f(12, "normal"))
            else:
                l.config(text="")
        if v["stop"] is not None:
            s = v["stop"]
            self.stop_l.config(text=f"FOUNTAIN {s:4.1f}s", fg=COL["good"] if s < 6 else COL["warn"] if s < 8 else COL["bad"])
        elif v["trip"] is not None and v["clock"] is not None:
            t = v["trip"]
            self.stop_l.config(text=f"{t.dest}  {v['clock'] - t.start:3.0f}s   +{t.lh_gain} LH", fg=ST_COL.get(t.dest, FG))
        else:
            self.stop_l.config(text="")
        tips = sorted(v["tips"], key=lambda t: {"bad": 0, "warn": 1, "good": 2, "info": 3}[t.level])[:3]
        for i, l in enumerate(self.tip_ls):
            if i < len(tips):
                l.config(text=("▲ " if tips[i].level in ("bad", "warn") else "• ") + tips[i].text, fg=COL[tips[i].level])
            else:
                l.config(text="")
        c = self.map_c; c.delete("hero")
        if v["pos"]:
            X, Y = self._xy(*v["pos"])
            c.create_oval(X - 8, Y - 8, X + 8, Y + 8, fill="#ffffff", outline="#ff2d55", width=3, tags="hero")
        if v["rec"] in DATA["stations"]:
            camps = DATA["stations"][v["rec"]]
            X, Y = self._xy(*self._real(sum(p["x"] for p in camps) / len(camps), sum(p["y"] for p in camps) / len(camps)))
            c.create_oval(X - 26, Y - 26, X + 26, Y + 26, outline="#ffffff", width=2, dash=(4, 3), tags="hero")
        tc = self.trips_c; tc.delete("all")
        for i, t in enumerate(v["trips"]):
            row, col = divmod(i, 8)
            x0, y0 = col * 37, row * 48
            tc.create_rectangle(x0, y0, x0 + 33, y0 + 26, fill=ST_COL.get(t.dest, "#555"), outline="")
            tc.create_text(x0 + 16, y0 + 13, text=t.dest if len(t.dest) == 1 else t.dest[:2], fill="#101418", font=("Segoe UI", 11, "bold"))
            sub = f"{t.length:.0f}s" if t.dest == "F" and t.length else (f"+{t.lh_gain}" if t.lh_gain else "0")
            bad = (t.dest == "F" and t.length and t.length > 8) or (t.dest != "F" and t.length and t.lh_gain == 0)
            tc.create_text(x0 + 16, y0 + 37, text=sub, fill=COL["bad"] if bad else DIM, font=("Segoe UI", 8))
        for (a, b, c2), (label, val, mark) in zip(self.chk, v["checklist"]):
            a.config(text=mark, fg=COL["good"] if mark == "✓" else COL["bad"] if mark == "✗" else DIM)
            b.config(text=label); c2.config(text=val)

    def _log_runs(self):
        e = self.eng
        if not e.minute_log or e.hero_name != "npc_dota_hero_tinker" or e.bot_run:
            return
        done = getattr(self, "_logged", {})
        key = e.game_id or "?"
        start = done.get(key, 0)
        rows = e.minute_log[start:]
        if not rows:
            return
        new = not RUNS.exists()
        with open(RUNS, "a", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=RUN_FIELDS)
            if new:
                w.writeheader()
            for r in rows:
                w.writerow({"session": SESSION_ID, "match": key, "hero": "tinker", "team": e.team, **r})
        done[key] = len(e.minute_log)
        self._logged = done

    def _maybe_summary(self):
        self._log_runs()
        e = self.eng
        if e.summary_written or e.clock is None or e.clock < 600 or not e.keen_level or e.bot_run:
            return
        e.summary_written = True
        row = e.summary_row()
        # one row per game, and only for a run the coach actually followed (not a restart on the end screen)
        if e.first_camp_kill is None or e.keen_learned_at is None or e.keen_learned_at > 540:
            return
        if SCORESHEET.exists() and any(r.get("match") == str(row["match"]) for r in csv.DictReader(open(SCORESHEET, encoding="utf-8"))):
            return
        append_row(SCORESHEET, row)


def main():
    global PORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--record", type=pathlib.Path, help="session file (default: sessions/<date_time>.jsonl)")
    ap.add_argument("--no-record", action="store_true", help="don't save the session")
    ap.add_argument("--port", type=int, default=PORT, help="GSI port (must match the .cfg)")
    ap.add_argument("--advisor", choices=["jev", "shadow", "rules"], default=None,
                    help="jev: Jev picks the next station · shadow: rules pick, Jev logged · rules: no Jev "
                         "(default: rules, no Jev calls)")
    a = ap.parse_args()
    PORT = a.port
    if a.install:
        install()
        return
    q: queue.Queue = queue.Queue()
    try:
        if not a.record and not a.no_record:
            SESSIONS.mkdir(exist_ok=True)
            a.record = SESSIONS / time.strftime("%Y-%m-%d_%H%M.jsonl")
        srv = start_server(q, None if a.no_record else a.record)
    except OSError as ex:
        msg = f"Tinker Coach is already running (port {PORT} is in use).\n\n{ex}"
        print(msg)
        try:                                   # pythonw has no console: show it
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, msg, "Tinker Coach", 0x40)
        except Exception:
            pass
        return
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # real pixels, so the minimap overlay lines up
    settings = overlays.load_settings()
    import ctypes as _ct
    sw, sh = _ct.windll.user32.GetSystemMetrics(0), _ct.windll.user32.GetSystemMetrics(1)
    hudcfg = overlays.dota_hud_settings()
    if not settings.get("minimap_manual") or not settings.get("minimap"):
        settings["minimap"] = overlays.dota_minimap_rect(sw, sh, hudcfg)
    hud_auto = not (settings.get("hud_manual") and settings.get("hud_pos"))

    def hud_spot(rect, flip):
        mx, my, ms = rect
        on_right = not flip                     # dota_hud_flip = true is Dota's normal, minimap-left layout
        return [max(0, mx + ms - overlays.Hud.W), max(0, my - overlays.Hud.H - 12)] if on_right \
            else [max(0, mx + 8), max(0, my - overlays.Hud.H - 12)]
    if hud_auto:
        settings["hud_pos"] = hud_spot(settings["minimap"], hudcfg["flip"])
    print(f"Minimap: {'left' if hudcfg['flip'] else 'right'}, size {hudcfg['size']} -> overlay {settings['minimap']}"
          f"{' (manual)' if settings.get('minimap_manual') else ''}")
    root = tk.Tk(); root.withdraw()
    panel_win = tk.Toplevel(root)
    panel = App(panel_win, q)
    import jev_advisor
    mode = a.advisor or "rules"                     # Jev only when asked for (--advisor jev)
    if mode != "rules":
        try:
            panel.eng.advisor = jev_advisor.JevAdvisor(mode, log=print)
            print(f"Jev advisor on ({mode}); decisions logged to jev_log.jsonl")
        except Exception as ex:
            print(f"Jev advisor off: {ex}")
    hud = overlays.Hud(root, settings)
    mm = overlays.MinimapOverlay(root, settings)
    hotkeys = overlays.Hotkeys([]); hotkeys.start()
    state = {"unlocked": False, "hidden": False}

    def persist():
        hx, hy = (hud.x, hud.y) if hasattr(hud, 'x') else (hud.win.winfo_x(), hud.win.winfo_y())
        settings.update(hud_pos=[hx, hy], minimap=mm.rect(),
                        panel_visible=panel_win.state() != "withdrawn",
                        minimap_manual=settings.get("minimap_manual") or mm.moved,
                        hud_manual=settings.get("hud_manual") or hud.moved)
        overlays.save_settings(settings)

    def toggle_panel():
        if panel_win.state() == "withdrawn":
            panel_win.deiconify(); panel_win.lift()
        else:
            panel_win.withdraw()
        persist()

    def action(name):
        if name == "unlock":
            state["unlocked"] = not state["unlocked"]
            hud.set_locked(not state["unlocked"]); mm.set_locked(not state["unlocked"])
            if state["unlocked"]:
                mm.win.focus_force()
            else:
                persist()
        elif name == "panel":
            toggle_panel()
        elif name == "quit":
            persist()
            root.after(300, root.destroy)
        elif name == "hide":
            state["hidden"] = not state["hidden"]
            hud.show(not state["hidden"] and settings["show_hud"])
            mm.show(not state["hidden"] and settings["show_minimap_overlay"])

    state["steamid"] = None

    drill_watch = drill.DrillWatcher(log=print)

    def overlay_tick():
        note = drill_watch.tick(panel.eng.clock, panel.eng.game_id, panel.eng.level)
        panel.eng.drill_note = note
        sid = panel.eng.steamid
        if sid and sid != state["steamid"]:
            state["steamid"] = sid
            if not (settings.get("minimap_manual") or mm.moved):
                cfg = overlays.dota_hud_settings(sid)
                rect = overlays.dota_minimap_rect(sw, sh, cfg)
                mm.place(rect)
                if hud_auto and not hud.moved:
                    x, y = hud_spot(rect, cfg["flip"])
                    if hasattr(hud, 'x'):
                        hud.x, hud.y, hud._sig = x, y, None
                    else:
                        hud.win.geometry(f"+{x}+{y}")
        while hotkeys.out:
            action(hotkeys.out.pop(0))
        if not state["hidden"]:
            hud.render(panel.eng)
            mm.render(panel.eng)

    panel.listeners.append(overlay_tick)
    # panel buttons for the same actions (the overlays themselves are click-through)
    bar = tk.Frame(panel_win, bg=BG); bar.pack(fill="x", side="bottom", padx=12)
    for txt, name in (("move overlays (Ctrl+Alt+U)", "unlock"), ("hide overlays (Ctrl+Alt+H)", "hide"),
                      ("quit coach (Ctrl+Alt+Q)", "quit")):
        tk.Button(bar, text=txt, command=lambda n=name: action(n), bg=PANEL, fg=FG, relief="flat",
                  activebackground="#2a323a", activeforeground=FG).pack(side="left", padx=(0, 6), pady=4)
    panel_win.protocol("WM_DELETE_WINDOW", toggle_panel)
    if not settings["panel_visible"]:
        panel_win.withdraw()
    if hotkeys.failed:
        print("Hotkeys already in use:", ", ".join(hotkeys.failed))
    print("Tinker Coach running. Ctrl+Alt+P panel · Ctrl+Alt+U move overlays · Ctrl+Alt+H hide · Ctrl+Alt+Q quit")
    try:
        root.mainloop()
    finally:
        persist()
        srv.shutdown()


if __name__ == "__main__":
    main()
