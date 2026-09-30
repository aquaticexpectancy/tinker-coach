"""Transparent, click-through overlays drawn on top of Dota (Borderless Window mode).

Nothing here talks to Dota: the windows only display what the engine computed from GSI.
Hotkeys (global):
    Ctrl+Alt+U  unlock / lock overlays (unlocked: drag to move, mouse wheel resizes the minimap overlay)
    Ctrl+Alt+P  show / hide the full panel
    Ctrl+Alt+H  hide / show all overlays
    Ctrl+Alt+Q  quit the coach
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import math
import pathlib
import threading
import time
import tkinter as tk
import tkinter.font as tkfont

import mapart
from engine import DATA, STATION_NAMES, fmt

HERE = pathlib.Path(__file__).parent
SETTINGS = HERE / "settings.json"
KEY = "#010203"                          # transparent colour key
FONT = "Segoe UI"
COL = {"good": "#3ecf73", "warn": "#ffc043", "bad": "#ff5a4a", "info": "#8ec5ff"}
ST_COL = {"F": "#c8d0d8", "A": "#39d27a", "B": "#ffb13d", "C": "#ff4d40", "D": "#c37cf0", "E": "#ff9d2e", "W": "#ffd24a",
          "lane": "#e0c040", "jungle": "#9aa4ad", "enemy": "#ff2d55", "?": "#9aa4ad"}

DEFAULTS = {
    "hud_pos": None,                     # None = placed next to the minimap automatically
    "minimap": None,                     # None = computed from your Dota HUD settings (see dota_minimap_rect)
    "minimap_manual": False,             # True once you've dragged it yourself (Ctrl+Alt+U)
    "show_minimap_overlay": True,
    "show_hud": True,
    "panel_visible": False,
}


# Dota's HUD stylesheet (panorama/styles/hud/hud_reborn.css), in 1080p reference pixels:
#   #minimap_block 244 (extra large 280, extra-extra large 420), anchored bottom-left,
#   #minimap 260 / 296 / 444 centred inside it (the map art spans the whole #minimap panel),
#   Dota's default layout keeps the minimap bottom-LEFT with dota_hud_flip = true (its own "Standard"
#   preset in cfg/dota_minimap.cfg sets it to 1); dota_hud_flip = false moves it bottom-right.
MINIMAP_SIZES = {0: (244, 260), 1: (280, 296), 2: (420, 444)}
STEAM = pathlib.Path(r"C:\Program Files (x86)\Steam")


def dota_hud_settings(steamid: str | None = None) -> dict:
    """Read dota_hud_flip / dota_hud_extra_large_minimap from the player's Steam cloud config."""
    import re
    files = []
    if steamid:
        try:
            acc = int(steamid) - 76561197960265728
            files.append(STEAM / "userdata" / str(acc) / "570" / "remote" / "user_convars.vcfg")
        except ValueError:
            pass
    if not steamid:                       # before GSI says who is playing: Steam's most recent login
        try:
            lu = (STEAM / "config" / "loginusers.vdf").read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'"(7656\d{13})"\s*\{(.*?)\n\t\}', lu, re.S):
                if re.search(r'"MostRecent"\s*"1"', m.group(2)):
                    files.append(STEAM / "userdata" / str(int(m.group(1)) - 76561197960265728) / "570" / "remote" / "user_convars.vcfg")
        except OSError:
            pass
    files += sorted(STEAM.glob("userdata/*/570/remote/user_convars.vcfg"), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files:
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        get = lambda k: (re.search(rf'"{k}"\s+"([^"]*)"', t) or [None, None])[1]
        return {"flip": (get("dota_hud_flip") or "false").lower() in ("true", "1"),
                "size": int(float(get("dota_hud_extra_large_minimap") or 0)), "file": str(f)}
    return {"flip": False, "size": 0, "file": None}


def dota_minimap_rect(screen_w: int, screen_h: int, hud: dict) -> list:
    s = screen_h / 1080
    block, mm = MINIMAP_SIZES.get(hud["size"], MINIMAP_SIZES[0])
    cont_w = min(screen_w, 2520 * s) if screen_w / screen_h > 2.2 else screen_w     # ultrawide: centred HUD
    cont_x = (screen_w - cont_w) / 2
    on_right = not hud["flip"]
    bx = cont_x + (cont_w - block * s if on_right else 0)
    by = screen_h - block * s
    off = (block - mm) / 2 * s
    return [round(bx + off), round(by + off), round(mm * s)]


def load_settings() -> dict:
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(SETTINGS.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s: dict):
    try:
        SETTINGS.write_text(json.dumps(s, indent=1), encoding="utf-8")
    except OSError:
        pass


# ------------------------------------------------------------------ win32 helpers
GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80000, 0x20, 0x80, 0x08000000
user32 = ctypes.windll.user32 if hasattr(ctypes, "windll") else None


def _hwnd(win: tk.Toplevel) -> int:
    win.update_idletasks()
    return user32.GetParent(win.winfo_id()) or win.winfo_id()


def set_click_through(win: tk.Toplevel, on: bool):
    if not user32:
        return
    h = _hwnd(win)
    st = user32.GetWindowLongW(h, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    st = st | WS_EX_TRANSPARENT if on else st & ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(h, GWL_EXSTYLE, st)


_FONTS: dict = {}


def fit(text: str, max_w: int, size: int, weight="bold", min_size: int = 9) -> tuple[str, int]:
    """Largest font size (down to min_size) at which text fits max_w pixels; trim with … if even that is too wide."""
    for s in range(size, min_size - 1, -1):
        f = _FONTS.setdefault((s, weight), tkfont.Font(family=FONT, size=s, weight=weight))
        if f.measure(text) <= max_w:
            return text, s
    f = _FONTS[(min_size, weight)]
    while len(text) > 4 and f.measure(text + "…") > max_w:
        text = text[:-1]
    return text.rstrip() + "…", min_size


def outlined(c: tk.Canvas, x, y, text, fill, size, weight="bold", anchor="nw", tags="", max_w=None):
    if max_w:
        text, size = fit(text, max_w, size, weight)
    """Text with a black outline so it reads on any part of the map."""
    font = (FONT, size, weight)
    w = 2 if size >= 14 else 1
    for dx in (-w, 0, w):
        for dy in (-w, 0, w):
            if dx or dy:
                c.create_text(x + dx, y + dy, text=text, fill="#000000", font=font, anchor=anchor, tags=tags)
    return c.create_text(x, y, text=text, fill=fill, font=font, anchor=anchor, tags=tags)


class _Overlay:
    def __init__(self, root, w, h, x, y):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=KEY)
        self.win.attributes("-transparentcolor", KEY)
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.c = tk.Canvas(self.win, width=w, height=h, bg=KEY, highlightthickness=0)
        self.c.pack(fill="both", expand=True)
        self.locked = True
        self.moved = False              # True once you drag it yourself (then it's remembered)
        self._drag = None
        self.c.bind("<ButtonPress-1>", self._start)
        self.c.bind("<B1-Motion>", self._move)
        self.win.after(50, lambda: set_click_through(self.win, True))

    def _start(self, e):
        self._drag = (e.x_root - self.win.winfo_x(), e.y_root - self.win.winfo_y())

    def _move(self, e):
        if not self.locked and self._drag:
            self.win.geometry(f"+{e.x_root - self._drag[0]}+{e.y_root - self._drag[1]}")
            self.moved = True

    def set_locked(self, locked: bool):
        self.locked = locked
        set_click_through(self.win, locked)

    def show(self, on: bool):
        (self.win.deiconify if on else self.win.withdraw)()
        if on:
            self.win.after(30, lambda: set_click_through(self.win, self.locked))


# ------------------------------------------------------------------ compact HUD
class Hud(_Overlay):
    W, H = 470, 118

    def __init__(self, root, settings):
        x, y = settings["hud_pos"]
        super().__init__(root, self.W, self.H, x, y)

    def render(self, eng):
        c = self.c
        c.delete("all")
        if not self.locked:
            c.create_rectangle(1, 1, self.W - 2, self.H - 2, outline="#ffffff", dash=(4, 3), width=2)
            outlined(c, self.W - 8, self.H - 6, "drag me · Ctrl+Alt+U to lock", "#ffffff", 9, anchor="se")
        if eng.clock is None:
            outlined(c, 6, 6, "Tinker Coach · waiting for Dota…", "#c8d0d8", 11, max_w=self.W - 12)
            return
        hero = eng.hero_name.replace("npc_dota_hero_", "")
        if not eng.hero_name or hero != "tinker":
            outlined(c, 6, 6, f"Tinker Coach · idle ({hero or 'no hero yet'})", "#9aa4ad", 10, "normal", max_w=self.W - 12)
            return
        v = eng.view()
        g = v["guide"]
        rec = v["rec"]
        # big station letter = where the next Keen goes
        outlined(c, 6, 0, rec, ST_COL.get(rec, "#fff"), 34)
        outlined(c, 8, 60, "NEXT", ST_COL.get(rec, "#fff"), 8)
        cur = g["steps"][g["cur"]] if g["steps"] and 0 <= g["cur"] < len(g["steps"]) else ""
        nxt = g["steps"][g["cur"] + 1] if g["steps"] and g["cur"] + 1 < len(g["steps"]) else ""
        room = self.W - 70
        outlined(c, 62, 4, "▶ " + cur, "#ffffff", 17, max_w=room)
        if nxt:
            outlined(c, 64, 38, "then  " + nxt, "#c8d0d8", 11, "normal", max_w=room)
        # line 3: fountain stopwatch or trip, plus the most urgent warning
        if v["stop"] is not None:
            s = v["stop"]
            outlined(c, 64, 62, f"FOUNTAIN {s:.0f}s", COL["good"] if s < 6 else COL["warn"] if s < 8 else COL["bad"], 12, max_w=room)
        elif v["clock"] >= 0:
            imm, _top = v["bench"]
            d = v["lh"] - imm
            txt = f"{fmt(v['clock'])} · LH {v['lh']} ({d:+.0f})"
            ok = d >= 0
            if v["net_worth"] is not None:
                nimm, _ = eng.bench_nw()
                dn = v["net_worth"] - nimm
                txt += f" · NW {v['net_worth']:,} ({dn:+,})"
                ok = dn >= 0
            outlined(c, 64, 62, txt + " vs Immortal", COL["good"] if ok else COL["warn"], 10, "normal", max_w=room)
        tips = sorted([t for t in v["tips"] if t.level in ("bad", "warn")], key=lambda t: t.level != "bad")
        if tips:
            outlined(c, 64, 86, "▲ " + tips[0].text, COL[tips[0].level], 11, max_w=room)


# ------------------------------------------------------------------ minimap overlay
class MinimapOverlay(_Overlay):
    def __init__(self, root, settings):
        x, y, self.S = settings["minimap"]
        super().__init__(root, self.S, self.S, x, y)
        self.t0 = time.time()
        self.c.bind("<MouseWheel>", self._wheel)
        self.win.bind("<Key>", self._key)

    def place(self, rect):
        x, y, self.S = rect
        self.win.geometry(f"{self.S}x{self.S}+{x}+{y}")
        self.c.config(width=self.S, height=self.S)

    def _wheel(self, e):
        self.moved = True
        if self.locked:
            return
        self.S = max(120, min(600, self.S + (4 if e.delta > 0 else -4)))
        self.win.geometry(f"{self.S}x{self.S}")
        self.c.config(width=self.S, height=self.S)

    def _key(self, e):
        if self.locked:
            return
        self.moved = True
        dx, dy = {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}.get(e.keysym, (0, 0))
        self.win.geometry(f"+{self.win.winfo_x() + dx}+{self.win.winfo_y() + dy}")

    def _xy(self, x, y):
        span = mapart.WORLD_MAX - mapart.WORLD_MIN
        return (x - mapart.WORLD_MIN) / span * self.S, (mapart.WORLD_MAX - y) / span * self.S

    def rect(self):
        return [self.win.winfo_x(), self.win.winfo_y(), self.S]

    def render(self, eng):
        c = self.c
        c.delete("all")
        real = (lambda x, y: (x, y)) if eng.team == "radiant" else (lambda x, y: (-x, -y))
        if not self.locked:
            # calibration: outline + every camp dot, line these up with Dota's minimap
            c.create_rectangle(1, 1, self.S - 2, self.S - 2, outline="#ffffff", dash=(4, 3), width=2)
            for st, camps in DATA["stations"].items():
                for cp in camps:
                    X, Y = self._xy(*real(cp["x"], cp["y"]))
                    c.create_oval(X - 3, Y - 3, X + 3, Y + 3, fill=ST_COL[st], outline="#000")
            X, Y = self._xy(*real(DATA["fountain"]["x"], DATA["fountain"]["y"]))
            c.create_oval(X - 6, Y - 6, X + 6, Y + 6, outline="#ffffff", width=2)
            outlined(c, self.S / 2, 4, "drag · wheel = size · arrows = nudge", "#ffffff", 8, anchor="n")
            outlined(c, self.S / 2, 18, "align dots/fountain ring with the minimap", "#ffffff", 8, anchor="n")
        if eng.clock is None or not eng.keen_level or eng.hero_name != "npc_dota_hero_tinker":
            return
        rec = eng.recommend()[0]
        pulse = 3 * math.sin((time.time() - self.t0) * 5)
        if rec in ("B", "W") and eng.wave_target:
            X, Y = self._xy(*eng.wave_target)          # already real coordinates
            r = 12 + pulse
            col = ST_COL.get(rec, "#fff")
            c.create_oval(X - r - 1, Y - r - 1, X + r + 1, Y + r + 1, outline="#000000", width=5)
            c.create_oval(X - r, Y - r, X + r, Y + r, outline=col, width=3)
            outlined(c, X + r, Y - r, "wave", col, 10, anchor="sw")
            return
        if rec not in DATA["stations"]:
            return
        camps = DATA["stations"][rec]
        pts = [self._xy(*real(p["x"], p["y"])) for p in camps]
        cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
        spread = max(math.hypot(px - cx, py - cy) for px, py in pts)
        r = spread + 10 + pulse
        col = ST_COL.get(rec, "#fff")
        c.create_oval(cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1, outline="#000000", width=5)
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=col, width=3)
        outlined(c, cx + r * 0.75, cy - r * 0.95, rec, col, 14, anchor="sw")


# ------------------------------------------------------------------ global hotkeys
class Hotkeys(threading.Thread):
    """RegisterHotKey on its own message loop; actions are handed back to Tk via a queue."""
    MOD = 0x0001 | 0x0002 | 0x4000      # Alt + Ctrl + no-repeat
    KEYS = {1: ("U", "unlock"), 2: ("P", "panel"), 4: ("H", "hide"), 5: ("Q", "quit")}

    def __init__(self, out):
        super().__init__(daemon=True)
        self.out = out
        self.failed = []

    def run(self):
        if not user32:
            return
        for i, (k, name) in self.KEYS.items():
            if not user32.RegisterHotKey(None, i, self.MOD, ord(k)):
                self.failed.append(f"Ctrl+Alt+{k}")
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == 0x0312:   # WM_HOTKEY
                self.out.append(self.KEYS.get(msg.wParam, ("", ""))[1])


# Pretty versions (per-pixel alpha, icons). These replace the Tk-canvas ones above.
try:
    from hud_gfx import Hud, MinimapOverlay  # noqa: E402,F811
except Exception as _ex:  # Pillow/numpy missing: keep the plain overlays
    print(f"Plain overlays ({_ex})")
