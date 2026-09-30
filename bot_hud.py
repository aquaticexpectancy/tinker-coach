"""The bot's "thinking" panel (transparent, click-through, top right) and the screen recorder.

BotHud draws what the bot is doing now, the last decision (every option with Jev's probability,
the pick, what the rules would have done, the facts Jev was given), a live score against your
best run, and the trip log. Recorder captures the whole screen, overlay included, to an .mp4
with ffmpeg (GPU encoder when available).
"""
from __future__ import annotations

import csv
import pathlib
import shutil
import subprocess
import time

from PIL import Image, ImageDraw

from hud_gfx import BAD, DIM, GOOD, INFO, SOFT, SS, ST_COL, WARN, WHITE, LayeredWindow, fit, font, icon, pill

HERE = pathlib.Path(__file__).parent
NAMES = {"A": "Mid pair (A)", "B": "Mid wave", "C": "Hard + ancients (C)", "D": "Top-side camps (D)",
         "E": "Far camps (E)", "F": "Fountain", "laser": "Laser one", "rearm_march": "Rearm + March",
         "attack": "Right-click", "keen_now": "Leave now", "rearm_laser": "Rearm + Laser"}
PANEL = (10, 13, 18, 226)
W = 420


COMPARE_SESSION = None       # set by bot.py --drill: compare with that F11 run of yours


def best_run_curve() -> tuple[str, list]:
    """Net worth per minute of your run to compare with: the drill run the bot started from (bot.py --drill),
    else your best laned run (highest net worth at 10:00)."""
    runs = HERE / "runs.csv"
    if not runs.exists():
        return "", []
    if COMPARE_SESSION:
        curve = {}
        for r in csv.DictReader(open(runs, encoding="utf-8")):
            if r["session"] == COMPARE_SESSION and r.get("net_worth"):
                curve[int(r["minute"])] = int(r["net_worth"])
        return COMPARE_SESSION, [curve.get(i) for i in range(0, 21)]
    from workshop import SAMPLE_MATCHES
    by, lh5 = {}, {}
    for r in csv.DictReader(open(runs, encoding="utf-8")):
        if r.get("net_worth") and r["match"] not in SAMPLE_MATCHES:
            by.setdefault(r["match"], {})[int(r["minute"])] = int(r["net_worth"])
            if r["minute"] == "5":
                lh5[r["match"]] = int(r["lh"] or 0)
    # the bot lanes from 0:00, so compare with runs where you laned too (15+ last hits at 5:00), not skip-to-5:00 drills
    best = max((m for m in by if 10 in by[m] and lh5.get(m, 0) >= 15), key=lambda m: by[m][10], default=None)
    if not best:
        return "", []
    return best, [by[best].get(i) for i in range(0, 21)]


class BotHud(LayeredWindow):
    def __init__(self, root, screen_w, screen_h):
        self.k = max(0.75, screen_h / 1080)
        super().__init__(root, int(screen_w - (W + 24) * self.k), int(96 * self.k))
        self.best_match, self.best = best_run_curve()
        self._sig = None

    def render(self, s: dict):
        sig = repr(s)
        if sig == self._sig:
            return
        self._sig = sig
        img = self._draw(s)
        k = self.k / SS
        self.push(img.resize((int(img.width * k), int(img.height * k)), Image.LANCZOS))

    # ------------------------------------------------------------------ drawing (at 2x, 1080p design size)
    def _draw(self, s: dict) -> Image.Image:
        X = SS
        w = W * X
        img = Image.new("RGBA", (w, 900 * X), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        pad = 16 * X
        y = pad
        # header
        d.text((pad, y), "TINKER × JEV", font=font("black", 17 * X), fill=WHITE + (255,), anchor="lt")
        tag = "LAB RUN · " + ("JEV DECIDES" if s.get("advisor") == "jev" else "RULES DECIDE")
        d.text((pad, y + 22 * X), tag, font=font("semibold", 10 * X), fill=INFO + (255,), anchor="lt")
        clock = s.get("clock")
        if clock is not None:
            c = int(clock)
            d.text((w - pad, y - 2 * X), f"{'-' if c < 0 else ''}{abs(c) // 60}:{abs(c) % 60:02d}", font=font("black", 26 * X),
                   fill=WHITE + (255,), anchor="rt")
        y += 46 * X
        # NOW
        y = self._section(d, y, "NOW", pad, w)
        now = s.get("now") or "Waiting for the game…"
        ic = s.get("now_icon")
        x0 = pad
        if ic and icon(ic, 30 * X):
            img.alpha_composite(icon(ic, 30 * X), (pad, y))
            x0 = pad + 38 * X
        t, f = fit(d, now, "bold", 17 * X, w - x0 - pad)
        d.text((x0, y + 15 * X), t, font=f, fill=WHITE + (255,), anchor="lm")
        y += 40 * X
        sub = s.get("now_sub")
        if sub:
            t, f = fit(d, sub, "regular", 12 * X, w - 2 * pad)
            d.text((pad, y), t, font=f, fill=SOFT + (255,), anchor="lt")
            y += 20 * X
        # DECISION
        dec = s.get("decision")
        if dec:
            y += 6 * X
            y = self._section(d, y, dec["title"], pad, w, right=dec.get("meta"))
            for opt, p in dec["bars"]:
                chosen = opt == dec["pick"]
                col = ST_COL.get(opt, INFO) if len(opt) == 1 else (GOOD if chosen else INFO)
                label = NAMES.get(opt, opt)
                d.text((pad, y + 9 * X), label, font=font("bold" if chosen else "regular", 12 * X),
                       fill=(WHITE if chosen else SOFT) + (255,), anchor="lm")
                bx0, bx1 = pad + 150 * X, w - pad - 44 * X
                d.rounded_rectangle((bx0, y + 3 * X, bx1, y + 15 * X), radius=6 * X, fill=(255, 255, 255, 22))
                if p is not None and p > 0.004:
                    d.rounded_rectangle((bx0, y + 3 * X, bx0 + max(12 * X, (bx1 - bx0) * p), y + 15 * X), radius=6 * X,
                                        fill=col + (255 if chosen else 120,))
                d.text((w - pad, y + 9 * X), "—" if p is None else f"{p * 100:.0f}%", font=font("semibold", 12 * X),
                       fill=(WHITE if chosen else DIM) + (255,), anchor="rm")
                if opt == dec.get("rules"):
                    d.text((bx0 - 6 * X, y + 9 * X), "rules", font=font("semibold", 9 * X), fill=WARN + (255,), anchor="rm")
                y += 20 * X
            y += 4 * X
            verdict, vcol = dec["verdict"]
            t, f = fit(d, verdict, "semibold", 12 * X, w - 2 * pad)
            d.text((pad, y), t, font=f, fill=vcol + (255,), anchor="lt")
            y += 20 * X
            for line in dec.get("facts", [])[:4]:
                t, f = fit(d, "· " + line, "regular", 11 * X, w - 2 * pad)
                d.text((pad, y), t, font=f, fill=DIM + (255,), anchor="lt")
                y += 16 * X
        # SCORE vs your best run
        y += 8 * X
        y = self._section(d, y, "BOT vs YOUR BEST RUN", pad, w)
        nw, lh = s.get("nw"), s.get("lh")
        mine = None
        if clock is not None and self.best:
            m = max(0, min(20, int(clock // 60)))
            a, b = self.best[m], self.best[min(20, m + 1)]
            if a is not None:
                mine = a if b is None else a + (b - a) * ((clock % 60) / 60)
        colw = (w - 2 * pad) / 3
        for i, (lab, val, col) in enumerate((("BOT NET WORTH", f"{nw:,}" if nw else "—", WHITE),
                                            ("YOUR BEST", f"{int(mine):,}" if mine else "—", SOFT),
                                            ("BOT LAST HITS", str(lh) if lh is not None else "—", WHITE))):
            x = pad + i * colw
            if lab == "YOUR BEST" and COMPARE_SESSION:
                lab = "YOU (F11 " + COMPARE_SESSION[-4:-2] + ":" + COMPARE_SESSION[-2:] + ")"
            d.text((x, y), lab, font=font("semibold", 9 * X), fill=DIM + (255,), anchor="lt")
            d.text((x, y + 14 * X), val, font=font("black", 20 * X), fill=col + (255,), anchor="lt")
        if nw and mine:
            diff = nw - mine
            pill(d, pad, y + 44 * X, f"{'+' if diff >= 0 else ''}{int(diff):,} vs you", GOOD if diff >= 0 else BAD, 20 * X)
            y += 26 * X
        y += 48 * X
        # trips
        trips = s.get("trips") or []
        if trips:
            y = self._section(d, y, "TRIPS", pad, w)
            x = pad
            for tr in trips[-8:]:
                st = tr["station"]
                label = f"{st} +{tr['last_hits']}"
                nx = pill(d, x, y, label, ST_COL.get(st, INFO), 20 * X)
                x = nx + 5 * X
                if x > w - 70 * X:
                    x = pad
                    y += 26 * X
            y += 30 * X
        end = s.get("end")
        if end:
            y = self._section(d, y, "RESULT", pad, w)
            d.text((pad, y), end, font=font("bold", 14 * X), fill=WHITE + (255,), anchor="lt")
            y += 26 * X
        h = y + pad
        card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        cd = ImageDraw.Draw(card)
        cd.rounded_rectangle((0, 0, w - 1, h - 1), radius=18 * X, fill=PANEL, outline=(255, 255, 255, 34), width=X)
        card.alpha_composite(img.crop((0, 0, w, h)))
        return card

    @staticmethod
    def _section(d, y, title, pad, w, right=None):
        d.text((pad, y), title.upper(), font=font("bold", 10 * SS), fill=DIM + (255,), anchor="lt")
        if right:
            d.text((w - pad, y), right, font=font("semibold", 10 * SS), fill=DIM + (255,), anchor="rt")
        d.line((pad, y + 16 * SS, w - pad, y + 16 * SS), fill=(255, 255, 255, 26), width=SS)
        return y + 24 * SS


# ---------------------------------------------------------------------- screen recorder
def ffmpeg_path() -> str | None:
    p = shutil.which("ffmpeg")
    if p:
        return p
    for base in (pathlib.Path.home() / "AppData/Local/Microsoft/WinGet/Packages",):
        for exe in base.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"):
            return str(exe)
    return None


class Recorder:
    """Screen capture to .mp4, cropped to the Dota window. GPU path first (desktop duplication + the NVIDIA
    encoder through Windows Media Foundation), CPU fallback (gdigrab + x264)."""

    def __init__(self, out: pathlib.Path, fps: int = 60):
        self.out, self.fps, self.proc, self.log = out, fps, None, out.with_suffix(".ffmpeg.log")

    @staticmethod
    def dota_rect():
        """(x, y, w, h) of the Dota game window's client area in screen pixels, or None."""
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32
        best = []

        def cb(hwnd, _):
            if not user32.IsWindowVisible(hwnd):
                return True
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
            name = ""
            if h:
                buf = ctypes.create_unicode_buffer(1024)
                size = wt.DWORD(1024)
                if ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    name = buf.value.lower()
                ctypes.windll.kernel32.CloseHandle(h)
            if name.endswith("dota2.exe"):
                r = wt.RECT()
                user32.GetClientRect(hwnd, ctypes.byref(r))
                pt = wt.POINT(0, 0)
                user32.ClientToScreen(hwnd, ctypes.byref(pt))
                w, hh = r.right - r.left, r.bottom - r.top
                if w >= 800 and hh >= 600:
                    best.append((w * hh, pt.x, pt.y, w, hh))
            return True

        proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        user32.EnumWindows(proto(cb), 0)
        if not best:
            return None
        _, x, y, w, h = max(best)          # the game view is the biggest dota2.exe window (tools add small ones)
        return x, y, w - w % 2, h - h % 2

    def start(self) -> bool:
        exe = ffmpeg_path()
        if not exe:
            print("No ffmpeg: the run is logged but not filmed (see README: Jev bot video).")
            return False
        rect = self.dota_rect()
        dda = f"ddagrab=output_idx=0:framerate={self.fps}:draw_mouse=0"
        gdi = ["-f", "gdigrab", "-framerate", str(self.fps), "-draw_mouse", "0"]
        if rect:
            x, y, w, h = rect
            dda += f":offset_x={x}:offset_y={y}:video_size={w}x{h}"
            gdi += ["-offset_x", str(x), "-offset_y", str(y), "-video_size", f"{w}x{h}"]
        attempts = [
            ("GPU", [exe, "-y", "-hide_banner", "-f", "lavfi", "-i", dda + ",hwdownload,format=bgra",
                     "-c:v", "h264_mf", "-hw_encoding", "1", "-b:v", "10M", "-pix_fmt", "nv12", "-t", "1800", str(self.out)]),
            ("CPU", [exe, "-y", "-hide_banner", *gdi, "-i", "desktop",
                     "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p", "-t", "1800", str(self.out)]),
        ]
        for i, (kind, cmd) in enumerate(attempts):
            log = self.log.with_name(self.log.stem + f".{kind.lower()}.log")
            fh = open(log, "w", encoding="utf-8")
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=fh, stderr=subprocess.STDOUT,
                                         creationflags=0x08000000)
            time.sleep(2.5)
            if self.proc.poll() is None:
                where = f"Dota window {rect[2]}x{rect[3]}" if rect else "whole screen"
                print(f"Recording {where} to {self.out} ({kind} encoder)")
                return True
        print(f"ffmpeg could not start recording; see {self.log.parent}")
        self.proc = None
        return False

    def stop(self):
        if not self.proc or self.proc.poll() is not None:
            return
        try:
            self.proc.stdin.write(b"q")               # ffmpeg finishes the file cleanly on 'q'
            self.proc.stdin.flush()
            self.proc.wait(timeout=20)
        except Exception:
            self.proc.kill()
        print(f"Video saved: {self.out}")
