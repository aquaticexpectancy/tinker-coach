"""Good-looking in-game overlays: rendered with Pillow, shown with per-pixel alpha.

Tk can only cut one colour out of a window, which gives jagged text on a hole in the
screen. These windows are Windows "layered" windows fed a premultiplied RGBA bitmap
(UpdateLayeredWindow), so we get a real frosted card, anti-aliased text, Dota's own
ability icons and a soft glow on the minimap ring. Still click-through when locked.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import math
import pathlib
import time
import tkinter as tk

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import mapart
from engine import DATA, STATION_NAMES, fmt

HERE = pathlib.Path(__file__).parent
SS = 2                                   # supersampling for smooth shapes

# ------------------------------------------------------------------ look
ST_COL = {"F": (200, 208, 216), "A": (57, 210, 122), "B": (255, 177, 61), "C": (255, 77, 64), "D": (195, 124, 240),
          "E": (255, 157, 46), "W": (255, 210, 74), "lane": (224, 192, 64), "jungle": (154, 164, 173),
          "enemy": (255, 45, 85), "?": (154, 164, 173)}
GOOD, WARN, BAD, INFO = (62, 207, 115), (255, 192, 67), (255, 90, 74), (142, 197, 255)
WHITE, SOFT, DIM = (244, 247, 250), (190, 199, 208), (128, 139, 150)
CARD = (12, 16, 21, 214)
SHORT = {"A": "MID PAIR", "B": "MID WAVE", "C": "HARD + ANCIENT", "D": "TOP-SIDE CAMPS", "E": "FAR CAMPS",
         "F": "FOUNTAIN", "W": "SIDE WAVE"}

_FONT_FILES = {"regular": "segoeui.ttf", "semibold": "seguisb.ttf", "bold": "segoeuib.ttf", "black": "seguibl.ttf"}
_fonts: dict = {}


def font(weight: str, size: float) -> ImageFont.FreeTypeFont:
    key = (weight, round(size))
    if key not in _fonts:
        for name in (_FONT_FILES.get(weight), "segoeuib.ttf", "arial.ttf"):
            try:
                _fonts[key] = ImageFont.truetype(f"C:/Windows/Fonts/{name}", round(size))
                break
            except OSError:
                continue
    return _fonts[key]


_icons: dict = {}


def icon(name: str, size: int) -> Image.Image | None:
    key = (name, size)
    if key not in _icons:
        p = HERE / "icons" / f"{name}.png"
        if not p.exists():
            _icons[key] = None
        else:
            im = Image.open(p).convert("RGBA")
            side = min(im.size)
            im = im.crop(((im.width - side) // 2, (im.height - side) // 2, (im.width + side) // 2, (im.height + side) // 2))
            im = im.resize((size, size), Image.LANCZOS)
            mask = Image.new("L", (size * 4, size * 4), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, size * 4 - 1, size * 4 - 1), radius=size * 4 // 5, fill=255)
            im.putalpha(mask.resize((size, size), Image.LANCZOS))
            _icons[key] = im
    return _icons[key]


def step_icon(text: str) -> str | None:
    t = text.lower()
    for word, name in (("march", "march"), ("rearm", "rearm"), ("laser", "laser"), ("keen", "keen"),
                       ("bottle", "bottle"), ("blink", "blink"), ("shove", "march"), ("wave", "march")):
        if word in t:
            return name
    return None


def fit(draw: ImageDraw.ImageDraw, text: str, weight: str, size: float, max_w: float, min_size: float = 9 * SS):
    s = size
    while s > min_size and draw.textlength(text, font=font(weight, s)) > max_w:
        s -= 1
    f = font(weight, s)
    if draw.textlength(text, font=f) > max_w:
        while len(text) > 3 and draw.textlength(text + "…", font=f) > max_w:
            text = text[:-1]
        text = text.rstrip() + "…"
    return text, f


def pill(draw, x, y, text, col, h, weight="semibold", size=None):
    size = size or h * 0.58
    f = font(weight, size)
    w = draw.textlength(text, font=f) + h * 0.9
    light = tuple(min(255, int(c + (255 - c) * 0.45)) for c in col)      # brighter text on a darker pill
    draw.rounded_rectangle((x, y, x + w, y + h), radius=h / 2, fill=col + (40,), outline=col + (140,), width=max(1, SS))
    draw.text((x + h * 0.45, y + h / 2), text, font=f, fill=light + (255,), anchor="lm")
    return x + w


# ------------------------------------------------------------------ layered window
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


user32.GetDC.restype = ctypes.c_void_p
user32.GetDC.argtypes = [ctypes.c_void_p]
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.CreateCompatibleDC.restype = ctypes.c_void_p
gdi32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
gdi32.CreateDIBSection.restype = ctypes.c_void_p
gdi32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.POINTER(BITMAPINFO), wt.UINT, ctypes.POINTER(ctypes.c_void_p),
                                   ctypes.c_void_p, wt.DWORD]
gdi32.SelectObject.restype = ctypes.c_void_p
gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
user32.UpdateLayeredWindow.argtypes = [wt.HWND, ctypes.c_void_p, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE),
                                       ctypes.c_void_p, ctypes.POINTER(wt.POINT), wt.DWORD,
                                       ctypes.POINTER(BLENDFUNCTION), wt.DWORD]
GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x80000, 0x20, 0x80, 0x08000000, 0x8


class LayeredWindow:
    def __init__(self, root, x, y):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.geometry(f"1x1+{x}+{y}")
        self.x, self.y = x, y
        self.locked = True
        self.moved = False
        self._drag = None
        self._img = None
        self.win.update_idletasks()
        self.hwnd = user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
        self._style(click_through=True)
        self.win.bind("<ButtonPress-1>", self._start)
        self.win.bind("<B1-Motion>", self._move)

    def _style(self, click_through):
        st = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TOPMOST
        st = st | WS_EX_TRANSPARENT if click_through else st & ~WS_EX_TRANSPARENT
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, st)

    def set_locked(self, locked: bool):
        self.locked = locked
        self._style(click_through=locked)

    def show(self, on: bool):
        (self.win.deiconify if on else self.win.withdraw)()
        if on:
            self._style(click_through=self.locked)
            if self._img is not None:
                self.push(self._img)

    def _start(self, e):
        self._drag = (e.x_root - self.x, e.y_root - self.y)

    def _move(self, e):
        if not self.locked and self._drag:
            self.x, self.y = e.x_root - self._drag[0], e.y_root - self._drag[1]
            self.moved = True
            if self._img is not None:
                self.push(self._img)

    def push(self, img: Image.Image):
        """Show an RGBA image with per-pixel alpha at (self.x, self.y)."""
        self._img = img
        w, h = img.size
        a = np.asarray(img, dtype=np.uint16)
        alpha = a[..., 3:4]
        rgb = (a[..., :3] * alpha // 255).astype(np.uint8)
        bgra = np.dstack([rgb[..., 2], rgb[..., 1], rgb[..., 0], alpha[..., 0].astype(np.uint8)]).tobytes()
        self.win.geometry(f"{w}x{h}+{self.x}+{self.y}")
        screen = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(screen)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth, bmi.bmiHeader.biHeight = w, -h
        bmi.bmiHeader.biPlanes, bmi.bmiHeader.biBitCount = 1, 32
        bits = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        ctypes.memmove(bits, bgra, len(bgra))
        old = gdi32.SelectObject(mem, hbmp)
        blend = BLENDFUNCTION(0, 0, 255, 1)
        user32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(wt.POINT(self.x, self.y)), ctypes.byref(wt.SIZE(w, h)),
                                   mem, ctypes.byref(wt.POINT(0, 0)), 0, ctypes.byref(blend), 2)
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)


# ------------------------------------------------------------------ HUD card
class Hud(LayeredWindow):
    W, H = 440, 156                      # 1080p design size (also used by coach.py to place it)

    def __init__(self, root, settings):
        x, y = settings["hud_pos"]
        super().__init__(root, x, y)
        self._sig = None

    def render(self, eng):
        v = eng.view() if eng.clock is not None and eng.hero_name == "npc_dota_hero_tinker" else None
        sig = (repr(v and (v["rec"], v["guide"], v["stop"] and round(v["stop"], 1), v["lh"], v["net_worth"],
                             [t.text for t in v["tips"]], v["camp"], int(v["clock"]))) , self.locked, eng.clock is None,
               eng.hero_name)
        if sig == self._sig:
            return
        self._sig = sig
        self.push(self._draw(eng, v))

    def _idle(self, text):
        W, H = 330 * SS, 36 * SS
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((0, 0, W - 1, H - 1), radius=H / 2, fill=CARD, outline=(255, 255, 255, 30), width=SS)
        d.ellipse((14 * SS, H / 2 - 5 * SS, 24 * SS, H / 2 + 5 * SS), fill=DIM + (255,))
        t, f = fit(d, text, "semibold", 13 * SS, W - 44 * SS)
        d.text((34 * SS, H / 2), t, font=f, fill=SOFT + (255,), anchor="lm")
        return self._finish(img)

    def _finish(self, img):
        img = img.resize((img.width // SS, img.height // SS), Image.LANCZOS)
        if not self.locked:
            d = ImageDraw.Draw(img)
            d.rounded_rectangle((1, 1, img.width - 2, img.height - 2), radius=14, outline=(255, 255, 255, 220), width=2)
            d.text((img.width - 10, img.height - 8), "drag · Ctrl+Alt+U to lock", font=font("semibold", 11), fill=WHITE + (255,), anchor="rs")
        return img

    def _draw(self, eng, v):
        if eng.clock is None:
            return self._idle("Tinker Coach · waiting for Dota")
        if v is None:
            hero = eng.hero_name.replace("npc_dota_hero_", "") or "no hero yet"
            return self._idle(f"Tinker Coach · idle ({hero})")
        W, H = self.W * SS, self.H * SS
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        rec = v["rec"]
        col = ST_COL.get(rec, WHITE)
        # card + accent
        d.rounded_rectangle((0, 0, W - 1, H - 1), radius=18 * SS, fill=CARD, outline=(255, 255, 255, 26), width=SS)
        d.rounded_rectangle((0, 18 * SS, 4 * SS, H - 18 * SS), radius=2 * SS, fill=col + (255,))
        # station badge
        bx, by, bs = 16 * SS, 16 * SS, 66 * SS
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle((bx - 4 * SS, by - 4 * SS, bx + bs + 4 * SS, by + bs + 4 * SS), radius=18 * SS, fill=col + (90,))
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(8 * SS)))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((bx, by, bx + bs, by + bs), radius=15 * SS, fill=col + (255,))
        d.text((bx + bs / 2, by + bs / 2 + 1 * SS), rec if len(rec) == 1 else rec[:1].upper(), font=font("black", 40 * SS),
               fill=(14, 18, 22, 255), anchor="mm")
        d.text((bx + bs / 2, by + bs + 12 * SS), "NEXT", font=font("bold", 10 * SS), fill=col + (255,), anchor="mm")
        # header: station + clock
        x0 = 98 * SS
        right = W - 16 * SS
        d.text((x0, 17 * SS), SHORT.get(rec, rec.upper()), font=font("bold", 11 * SS), fill=col + (255,), anchor="lm")
        clock = fmt(v["clock"]) if v["clock"] is not None and v["clock"] >= 0 else "pre-game"
        d.text((right, 17 * SS), clock, font=font("semibold", 11 * SS), fill=DIM + (255,), anchor="rm")
        # NOW: camp finisher overrides the plan once the March has done its work
        g = v["guide"]
        cur = g["steps"][g["cur"]] if g["steps"] and 0 <= g["cur"] < len(g["steps"]) else ""
        nxt = g["steps"][g["cur"] + 1] if g["steps"] and g["cur"] + 1 < len(g["steps"]) else ""
        camp = v.get("camp")
        if camp and camp["state"] in ("left", "clear"):
            cur = {"laser": "Laser the last one", "rearm": "Rearm → March", "keen": f"Keen → {rec}"}[camp["action"]]
            nxt = "" if camp["action"] == "keen" else f"Keen → {rec}"
        ic = step_icon(cur)
        iy, isz = 32 * SS, 40 * SS
        tx = x0
        if ic and icon(ic, isz):
            img.alpha_composite(icon(ic, isz), (x0, iy))
            d.rounded_rectangle((x0, iy, x0 + isz, iy + isz), radius=isz // 5, outline=(255, 255, 255, 60), width=SS)
            tx = x0 + isz + 12 * SS
        t, f = fit(d, cur, "bold", 21 * SS, right - tx)
        d.text((tx, iy + isz / 2), t, font=f, fill=WHITE + (255,), anchor="lm")
        # then
        y2 = 88 * SS
        if nxt:
            d.text((x0, y2), "then", font=font("semibold", 11 * SS), fill=DIM + (255,), anchor="lm")
            nx = x0 + 36 * SS
            ni = step_icon(nxt)
            if ni and icon(ni, 20 * SS):
                img.alpha_composite(icon(ni, 20 * SS), (nx, int(y2 - 10 * SS)))
                nx += 26 * SS
            t, f = fit(d, nxt, "semibold", 13 * SS, right - nx)
            d.text((nx, y2), t, font=f, fill=SOFT + (255,), anchor="lm")
        # pills: timer / camp state / LH / NW
        py, ph = 104 * SS, 20 * SS
        px = x0
        if v["stop"] is not None:
            s = v["stop"]
            px = pill(d, px, py, f"FOUNTAIN {s:.1f}s", GOOD if s < 6 else WARN if s < 8 else BAD, ph, "bold") + 6 * SS
        elif camp and camp["state"] == "working":
            px = pill(d, px, py, camp["text"], INFO, ph) + 6 * SS
        elif camp and camp["left"] is not None:
            px = pill(d, px, py, "camp clear" if camp["left"] == 0 else f"{camp['left']} left", GOOD if camp["left"] == 0 else WARN, ph) + 6 * SS
        if v["clock"] is not None and v["clock"] >= 0:
            imm, _ = v["bench"]
            dl = v["lh"] - imm
            px = pill(d, px, py, f"LH {v['lh']} {dl:+.0f}", GOOD if dl >= 0 else WARN, ph) + 6 * SS
            if v["net_worth"] is not None:
                nimm, _ = eng.bench_nw()
                dn = v["net_worth"] - nimm
                if px + 120 * SS < right:
                    pill(d, px, py, f"NW {v['net_worth']:,} {dn:+,}", GOOD if dn >= 0 else WARN, ph)
        # warning line
        tips = sorted([t for t in v["tips"] if t.level in ("bad", "warn")], key=lambda t: t.level != "bad")
        if tips:
            tc = BAD if tips[0].level == "bad" else WARN
            y4 = 138 * SS
            d.ellipse((x0, y4 - 4 * SS, x0 + 8 * SS, y4 + 4 * SS), fill=tc + (255,))
            t, f = fit(d, tips[0].text, "semibold", 12 * SS, right - x0 - 16 * SS)
            d.text((x0 + 14 * SS, y4), t, font=f, fill=tc + (255,), anchor="lm")
        return self._finish(img)


# ------------------------------------------------------------------ minimap ring
class MinimapOverlay(LayeredWindow):
    def __init__(self, root, settings):
        x, y, self.S = settings["minimap"]
        super().__init__(root, x, y)
        self.t0 = time.time()
        self.win.bind("<MouseWheel>", self._wheel)
        self.win.bind("<Key>", self._key)
        self._last = 0.0

    def place(self, rect):
        self.x, self.y, self.S = rect
        if self._img is not None:
            self._img = None

    def rect(self):
        return [self.x, self.y, self.S]

    def _wheel(self, e):
        if self.locked:
            return
        self.S = max(120, min(700, self.S + (4 if e.delta > 0 else -4)))
        self.moved = True

    def _key(self, e):
        if self.locked:
            return
        dx, dy = {"Left": (-1, 0), "Right": (1, 0), "Up": (0, -1), "Down": (0, 1)}.get(e.keysym, (0, 0))
        self.x += dx; self.y += dy; self.moved = True

    def _xy(self, x, y, S):
        span = mapart.WORLD_MAX - mapart.WORLD_MIN
        return (x - mapart.WORLD_MIN) / span * S, (mapart.WORLD_MAX - y) / span * S

    def render(self, eng):
        now = time.time()
        if now - self._last < 0.06:          # ~15 fps is plenty for the pulse
            return
        self._last = now
        S = self.S * SS
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        real = (lambda x, y: (x, y)) if eng.team == "radiant" else (lambda x, y: (-x, -y))
        if not self.locked:
            d = ImageDraw.Draw(img)
            d.rectangle((SS, SS, S - SS, S - SS), outline=(255, 255, 255, 230), width=2 * SS)
            for st, camps in DATA["stations"].items():
                for cp in camps:
                    X, Y = self._xy(*real(cp["x"], cp["y"]), S)
                    d.ellipse((X - 4 * SS, Y - 4 * SS, X + 4 * SS, Y + 4 * SS), fill=ST_COL[st] + (255,), outline=(0, 0, 0, 255))
            X, Y = self._xy(*real(DATA["fountain"]["x"], DATA["fountain"]["y"]), S)
            d.ellipse((X - 8 * SS, Y - 8 * SS, X + 8 * SS, Y + 8 * SS), outline=(255, 255, 255, 255), width=2 * SS)
            d.rounded_rectangle((S / 2 - 120 * SS, 6 * SS, S / 2 + 120 * SS, 40 * SS), radius=8 * SS, fill=(0, 0, 0, 170))
            d.text((S / 2, 16 * SS), "drag · wheel = size · arrows = nudge", font=font("semibold", 10 * SS), fill=WHITE + (255,), anchor="mm")
            d.text((S / 2, 30 * SS), "line the dots up with your minimap", font=font("regular", 10 * SS), fill=WHITE + (255,), anchor="mm")
        if eng.clock is not None and eng.keen_level and eng.hero_name == "npc_dota_hero_tinker":
            rec = eng.recommend()[0]
            col = ST_COL.get(rec, WHITE)
            target, spread = None, 0
            if rec in ("B", "W") and eng.wave_target:
                target, spread = self._xy(*eng.wave_target, S), 8 * SS
            elif rec in DATA["stations"]:
                pts = [self._xy(*real(p["x"], p["y"]), S) for p in DATA["stations"][rec]]
                cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
                target, spread = (cx, cy), max(math.hypot(px - cx, py - cy) for px, py in pts)
            if target:
                cx, cy = target
                pulse = (math.sin((now - self.t0) * 4.5) + 1) / 2
                r = spread + 12 * SS + pulse * 4 * SS
                glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
                ImageDraw.Draw(glow).ellipse((cx - r, cy - r, cx + r, cy + r), outline=col + (int(150 + 80 * pulse),), width=9 * SS)
                img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(5 * SS)))
                d = ImageDraw.Draw(img)
                d.ellipse((cx - r - SS, cy - r - SS, cx + r + SS, cy + r + SS), outline=(0, 0, 0, 200), width=5 * SS)
                d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col + (255,), width=3 * SS)
                bx, by, br = cx + r * 0.72, cy - r * 0.72, 10 * SS
                d.ellipse((bx - br, by - br, bx + br, by + br), fill=col + (255,), outline=(0, 0, 0, 220), width=2 * SS)
                d.text((bx, by + SS), rec, font=font("black", 12 * SS), fill=(14, 18, 22, 255), anchor="mm")
        sig = (self.S, self.x, self.y, self.locked, eng.team)
        if img.getbbox() is None and getattr(self, "_empty_sig", None) == sig:
            return                              # nothing to draw and nothing changed
        self._empty_sig = sig if img.getbbox() is None else None
        self.push(img.resize((self.S, self.S), Image.LANCZOS))
