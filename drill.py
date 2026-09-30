"""Skip laning: start the Tinker transition drill at level 6, 5:00, in a private cheats lobby.

Setup (once, done by `python coach.py --install`):
    cfg/tinker_drill.cfg      what F11 runs
    autoexec.cfg              + bind "F11" "exec tinker_drill"   (marked block, safe to delete)

In a lobby with "Enable cheats", pick Tinker, press F11 once:
    game starts, you're level 6 with laning gold, and the clock runs 10x (5:00 in ~30 s).
The coach notices the fast-forward (game clock outrunning real time, impossible in a real
match) and at ~4:55 rewrites tinker_drill.cfg to "normal speed" and presses F11 for you, then
puts the setup back for the next drill. It only presses the key when Dota is the focused window.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import pathlib
import time

KEY = "F11"
SCAN_F11 = 0x57
CFG_NAME = "tinker_drill"
MARK_BEGIN = "// >>> Tinker Coach drill key (safe to delete this block)"
MARK_END = "// <<< Tinker Coach drill key"
STOP_AT = 295            # game clock when the coach drops back to normal speed
SPEED = 10

# Real console cheats (names verified in Dota's server.dll). Chat cheats sent with `say`
# ("-lvlup", "-gold", "-startgame") are ignored by Dota, so they are not used.
SETUP = f"""// Tinker Coach drill: skip laning. Only works in a private lobby with "Enable cheats".
sv_cheats 1
dota_start_game
dota_give_gold 1400
host_timescale {SPEED}
"""
GO = """// Tinker Coach: drill reached 5:00, back to normal speed
host_timescale 1
dota_hero_refresh
"""


def cmd(line: str) -> str:
    return f"// Tinker Coach drill step\n{line}\n"


def dota_cfg_dir() -> pathlib.Path | None:
    for base in (r"C:\Program Files (x86)\Steam", r"C:\Program Files\Steam", r"D:\Steam", r"D:\SteamLibrary"):
        p = pathlib.Path(base) / "steamapps" / "common" / "dota 2 beta" / "game" / "dota" / "cfg"
        if p.exists():
            return p
    return None


def install() -> str:
    cfg = dota_cfg_dir()
    if not cfg:
        return "Dota cfg folder not found; drill key not installed."
    (cfg / f"{CFG_NAME}.cfg").write_text(SETUP, encoding="utf-8")
    auto = cfg / "autoexec.cfg"
    text = auto.read_text(encoding="utf-8", errors="replace") if auto.exists() else ""
    if MARK_BEGIN not in text:
        text = text.rstrip("\n") + f'\n{MARK_BEGIN}\nbind "{KEY}" "exec {CFG_NAME}"\n{MARK_END}\n'
        auto.write_text(text, encoding="utf-8")
    return f"Drill key: {KEY} -> exec {CFG_NAME} (restart Dota once so autoexec binds it)"


def _write(content: str):
    cfg = dota_cfg_dir()
    if cfg:
        (cfg / f"{CFG_NAME}.cfg").write_text(content, encoding="utf-8")


# ------------------------------------------------------------------ key press (Dota must be focused)
user32 = ctypes.windll.user32
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):      # largest union member: keeps sizeof(INPUT) right on x64
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def dota_focused() -> bool:
    hwnd = user32.GetForegroundWindow()
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
    if not h:
        return False
    try:
        size = wt.DWORD(1024)
        buf = ctypes.create_unicode_buffer(1024)
        ok = ctypes.windll.kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size))
        return bool(ok) and buf.value.lower().endswith("dota2.exe")
    finally:
        ctypes.windll.kernel32.CloseHandle(h)


def press_key():
    for up in (0, 2):
        inp = INPUT(type=1)
        inp.ki = KEYBDINPUT(0, SCAN_F11, 0x0008 | up, 0, 0)
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        time.sleep(0.05)


# ------------------------------------------------------------------ watcher (called by the coach every tick)
class DrillWatcher:
    TARGET_LEVEL = 6

    def __init__(self, log=print):
        self.log = log
        self.samples: list[tuple[float, float]] = []    # (wall, game clock)
        self.fast = False
        self.done_for = None                            # match we already brought back to normal speed
        self.level_for = None                           # match whose hero we already levelled
        self.probe = None                               # (level before, wall time) while testing dota_hero_level
        self.reset_at = None

    def _send(self, line):
        _write(cmd(line) if "\n" not in line else line)
        time.sleep(0.05)
        press_key()
        self.reset_at = time.time() + 2.5

    def tick(self, clock, match_id, level=0):
        now = time.time()
        if self.reset_at and now >= self.reset_at:      # put the setup back for the next drill
            _write(SETUP)
            self.reset_at = None
        if clock is None:
            return None
        self.samples.append((now, clock))
        self.samples = [s for s in self.samples if now - s[0] <= 3.0]
        if len(self.samples) >= 5:
            dw = self.samples[-1][0] - self.samples[0][0]
            dc = self.samples[-1][1] - self.samples[0][1]
            self.fast = dw > 1.0 and dc / dw > 3.0
        if not self.fast:
            return None
        if not dota_focused():
            return "Drill: click Dota so the coach can press F11"
        # 1) level to 6. dota_hero_level either SETS the level or ADDS levels; find out with one probe.
        if self.level_for != match_id and level and level < self.TARGET_LEVEL and not self.reset_at:
            if self.probe is None:
                self.probe = (level, now)
                self._send("dota_hero_level 2")
                return "Drill: levelling you to 6…"
            before, t = self.probe
            if now - t < 1.2:
                return "Drill: levelling you to 6…"
            if level == 2 and before != 2:              # it sets the level
                self._send(f"dota_hero_level {self.TARGET_LEVEL}")
            else:                                        # it adds levels (or nothing happened yet)
                self._send(f"dota_hero_level {self.TARGET_LEVEL - level}")
            self.level_for = match_id
            self.log(f"Drill: level {before} -> probe -> {level}; sent the rest")
            return "Drill: levelling you to 6…"
        # 2) back to normal speed just before 5:00
        if clock >= STOP_AT and self.done_for != match_id:
            _write(GO)
            time.sleep(0.05)
            press_key()
            self.done_for = match_id
            self.reset_at = now + 3.0
            self.log("Drill reached 5:00: normal speed")
            return None
        return f"Fast-forward to 5:00… ({int(clock)//60}:{int(clock)%60:02d})"
