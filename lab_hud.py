"""A small CLI-style progress window for the March lab or a bot batch (top right, always on top). Reads logs live.

    python lab_hud.py              the latest lab run or batch, whichever started last
    python lab_hud.py <run.jsonl>  that lab run
    python lab_hud.py --batch [batch.csv] [--runs N]   a bot_batch.py batch (default: the latest)

Lab: the family mix being tested now, time passed, ETA, families (combos) checked, tests done and a progress bar.
Batch: the game running now (setup, game clock), time passed, ETA, each setup's average so far and a progress bar.
Drag it with the left mouse button, right-click to close. Dota must be in Borderless Window mode to see it on top.
"""
import argparse
import csv
import glob
import json
import os
import re
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Claude Code colours (dark theme)
BG, FG, DIM, ORANGE, GREEN, RED, BAR_BG = "#1a1a1a", "#e8e6e3", "#8b8b8b", "#d97757", "#4eba65", "#e5534b", "#3a3a3a"
FONT = ("Cascadia Mono", 10)
BAR_W = 28
WIDTH = 64      # characters: no line may be longer (a long family line wrapped and pushed the bar out of the window)


def latest_lab():
    runs = [p for p in glob.glob(os.path.join(HERE, "bot_runs", "*.jsonl"))
            if '"lab_start"' in open(p, encoding="utf-8", errors="replace").read(20000)]
    return max(runs, key=os.path.getmtime) if runs else None


def short(names):
    out = []
    for fam in names.split(" + "):
        parts = fam.split("+")
        counts = {}
        for p in parts:
            p = (p.replace("polar_furbolg_", "furbolg ").replace("centaur_", "").replace("satyr_", "satyr ")
                 .replace("_thunder_lizard", " lizard").replace("frostbitten_golem", "frost golem").replace("_", " "))
            counts[p] = counts.get(p, 0) + 1
        out.append(", ".join(f"{k} x{v}" if v > 1 else k for k, v in counts.items()))
    return " | ".join(out)


class Window:
    def make_window(self, height):
        self.root = root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.94)
        root.configure(bg=BG)
        self.text = tk.Text(root, width=WIDTH, height=height, wrap="none", bg=BG, fg=FG, font=FONT, bd=0, highlightthickness=1,
                            highlightbackground="#2e2e2e", padx=12, pady=8, cursor="arrow")
        self.text.pack()
        for tag, col in (("orange", ORANGE), ("dim", DIM), ("green", GREEN), ("red", RED), ("barbg", BAR_BG)):
            self.text.tag_configure(tag, foreground=col)
        root.update_idletasks()
        w = root.winfo_reqwidth()
        root.geometry(f"+{root.winfo_screenwidth() - w - 16}+16")
        root.bind("<Button-3>", lambda e: root.destroy())
        root.bind("<ButtonPress-1>", self._grab)
        root.bind("<B1-Motion>", self._drag)
        self.tick()

    def _grab(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")


class Hud(Window):
    def __init__(self, path):
        self.path, self.pos, self.start, self.total, self.results, self.ended = path, 0, None, None, [], False
        self.queue = None
        self.make_window(7)

    def read(self):
        try:
            with open(self.path, encoding="utf-8", errors="replace") as f:
                f.seek(self.pos)
                for line in f:
                    if not line.endswith("\n"):
                        break
                    self.pos += len(line.encode("utf-8"))
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    k = r.get("kind")
                    if k == "lab_start":
                        self.start, self.total = r.get("wall"), r.get("tests")
                    elif k == "lab_result":
                        self.results.append(r)
                    elif k == "end":
                        self.ended = True
        except OSError:
            pass

    def build_queue(self):
        """The lab's test order (combos x March level x Marches x Laser x repeats), to name the test running now."""
        try:
            import bot
            cfg = bot.lab_config(argparse.Namespace(lab=1, lab_stations="A,C,D,E", lab_map="creeptests", lab_probe=None))
        except Exception:
            return None
        per = [(c, ml, n, l) for c in cfg["combos"] for ml in cfg["march_levels"] for n in cfg["marches"] for l in cfg["lasers"]]
        reps = max(1, (self.total or len(per)) // max(1, len(per)))
        return per * reps

    def tick(self):
        self.read()
        if self.total and self.queue is None:
            self.queue = self.build_queue() or []
        total = self.total or 0
        done = min(len(self.results), total) if total else len(self.results)   # a few tests can log twice
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", "* ", "orange")
        t.insert("end", "Tinker March lab\n", "orange")
        if not self.start:
            t.insert("end", "  waiting for the lab to start…\n", "dim")
        else:
            now = time.time()
            elapsed = now - self.start
            rate = done / elapsed if elapsed > 0 and done else 0
            eta = (total - done) / rate if rate and done < total else None
            if self.ended or done >= total:
                status, scol = "done", "green"
            elif self.results and now - self.results[-1]["wall"] > 30:
                status, scol = "stalled (no result for 30 s)", "red"
            else:
                status, scol = "running", "green"
            cur = self.queue[done] if self.queue and done < len(self.queue) else None
            if cur:
                c, ml, n, l = cur
                fams = " + ".join("+".join(sp["family"]) for sp in c["spawns"])
                t.insert("end", "  testing  ", "dim")
                t.insert("end", f"{c['station']} · March {ml} · {n}M{('+Laser' if l == 1 else '+Laser max HP') if l else ''}\n")
                t.insert("end", "  family   ", "dim")
                fam = short(fams)
                room = WIDTH - len("  family   ")
                t.insert("end", (fam if len(fam) <= room else fam[:room - 1] + "…") + "\n")
            else:
                t.insert("end", "  testing  -\n  family   -\n", "dim")
            combos_total = len({json.dumps(q[0]) for q in self.queue}) if self.queue else 0
            per_combo = (total // combos_total) if combos_total else 16
            t.insert("end", "  elapsed  ", "dim")
            t.insert("end", f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}")
            t.insert("end", "   eta  ", "dim")
            t.insert("end", f"{int(eta // 60):02d}:{int(eta % 60):02d}" if eta else "--:--")
            t.insert("end", "   done ≈ ", "dim")
            t.insert("end", (time.strftime("%H:%M", time.localtime(now + eta)) if eta else "--:--") + "\n")
            t.insert("end", "  families ", "dim")
            t.insert("end", f"{done // per_combo}/{combos_total or '?'}")
            t.insert("end", "   tests  ", "dim")
            t.insert("end", f"{done}/{total} checked\n")
            frac = done / total if total else 0
            fill = int(round(frac * BAR_W))
            t.insert("end", "  ")
            t.insert("end", "█" * fill, "green")
            t.insert("end", "░" * (BAR_W - fill), "barbg")
            t.insert("end", f" {frac * 100:5.1f}%\n", "green")
            t.insert("end", "  ● ", scol)
            t.insert("end", status, scol)
        t.configure(state="disabled")
        self.root.after(1000, self.tick)


def latest_batch():
    runs = glob.glob(os.path.join(HERE, "bot_runs", "batch_*.csv"))
    return max(runs, key=os.path.getmtime) if runs else None


def clock(sec):
    return f"{int(sec // 60):02d}:{int(sec % 60):02d}"


DRILL_FROM, DRILL_TO = 300, 600      # the drill plays 5:00 -> 10:00 game time


class BatchHud(Window):
    """Follows bot_batch.py: its CSV (finished games), batch_status.json (the plan, batches after 10-01 19:55) and
    the game log being written now. A batch without a status file: the plan is guessed from the CSV (setups in the
    order they first appear, round-robin, --runs each). The first setup is the baseline of the net worth column."""

    def __init__(self, path, runs, window=True):
        self.path, self.runs = path, runs
        self.base = os.path.splitext(os.path.basename(path))[0]
        self.game, self.game_pos, self.game_clock, self.game_wall, self.game_nw = None, 0, None, None, None
        self.game_speed, self.infos = None, {}
        self.rows, self.order, self.start, self.status = [], [], None, {}
        self.read()
        if window:                                                 # lab_tele.py reads the same state, no window
            self.make_window(8 + max(2, len(set(self.order))))

    def read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                self.rows = list(csv.DictReader(f))
        except OSError:
            self.rows = []
        st = {}
        try:
            with open(os.path.join(HERE, "bot_runs", "batch_status.json"), encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            pass
        if st.get("csv") == os.path.basename(self.path):
            self.status, self.order, self.start = st, st["order"], st["start"]
        else:
            setups = list(dict.fromkeys(r["setup"] for r in self.rows))
            self.order = [s for _ in range(self.runs) for s in setups]
            try:
                self.start = time.mktime(time.strptime(self.base, "batch_%Y-%m-%d_%H%M"))
            except ValueError:
                self.start = os.path.getctime(self.path)
        # the game now: the newest game log since the batch started that isn't in the CSV yet
        done = {r["run"] for r in self.rows}
        logs = [p for p in glob.glob(os.path.join(HERE, "bot_runs", "20*.jsonl"))
                if os.path.basename(p) not in done and os.path.getmtime(p) >= self.start]
        newest = max(logs, key=os.path.getmtime) if logs else None
        if newest != self.game:
            self.game, self.game_pos, self.game_clock, self.game_wall, self.game_nw = newest, 0, None, None, None
            self.game_speed = None
        if not self.game:
            return
        try:
            with open(self.game, encoding="utf-8", errors="replace") as f:
                f.seek(self.game_pos)
                for line in f:
                    if not line.endswith("\n"):
                        break
                    self.game_pos += len(line.encode("utf-8"))
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if r.get("clock") is not None:
                        self.game_clock = r["clock"]
                    if r.get("wall"):
                        self.game_wall = r["wall"]
                    if r.get("nw") is not None:
                        self.game_nw = r["nw"]
                    if r.get("kind") == "speed":
                        self.game_speed = r.get("x")
        except OSError:
            pass

    def avg_nw(self, setup):
        ok = [float(r["nw"]) for r in self.rows if r["setup"] == setup and r["status"] == "ok"]
        return sum(ok) / len(ok) if ok else None

    def run_info(self, run):
        """(jungle speed, real seconds for 5:00 -> 10:00) of a finished game, from its log; cached."""
        if run in self.infos:
            return self.infos[run]
        speed, w0, w1 = None, None, None
        try:
            for line in open(os.path.join(HERE, "bot_runs", run), encoding="utf-8", errors="replace"):
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                c, w = r.get("clock"), r.get("wall")
                if r.get("kind") == "speed" and c is not None and c < DRILL_TO - 1:
                    speed = r.get("x")                        # the last change before 10:00 = the jungle speed
                if c is not None and w and c >= DRILL_FROM:
                    w0 = w0 or w
                    w1 = w
        except OSError:
            pass
        self.infos[run] = (speed, (w1 - w0) if w0 and w1 else None)
        return self.infos[run]

    def setup_info(self, setup):
        """(speed, average real seconds a game) over a setup's finished games."""
        infos = [self.run_info(r["run"]) for r in self.rows if r["setup"] == setup and r.get("run")]
        speeds = {s for s, _ in infos if s}
        secs = [d for _, d in infos if d]
        speed = "/".join(f"{s:g}x" for s in sorted(speeds)) if speeds else None
        return speed, (sum(secs) / len(secs) if secs else None)

    def tick(self):
        self.read()
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        setups = list(dict.fromkeys(self.order)) or list(dict.fromkeys(r["setup"] for r in self.rows))
        base = setups[0] if setups else None
        t.insert("end", "* ", "orange")
        t.insert("end", "Tinker bot batch  ", "orange")
        t.insert("end", " vs ".join(setups) + "\n", "dim")
        total, done, now = len(self.order), len(self.rows), time.time()
        finished = bool(self.status.get("done")) or bool(total and done >= total)
        frac_game = 0.0
        if not finished and self.game_clock is not None:
            frac_game = min(1.0, max(0.0, (self.game_clock - DRILL_FROM) / (DRILL_TO - DRILL_FROM)))
        cur = self.order[done] if done < total else None
        t.insert("end", "  game     ", "dim")
        if finished:
            t.insert("end", f"{done}/{total} played\n")
        else:
            t.insert("end", f"{done + 1}/{total or '?'}  ")
            t.insert("end", cur or "?", "orange")
            if self.game_speed and (self.game_clock or 0) >= DRILL_FROM - 5:
                t.insert("end", f" {self.game_speed:g}x", "orange")
            t.insert("end", "  clock ", "dim")
            gs = self.status.get("game_start")
            if self.game_clock is None:                           # nothing logged yet: Dota launching / loading (~80 s)
                t.insert("end", "Dota loading" + (f" {clock(now - gs)}" if gs else "…") + "\n", "dim")
            elif self.game_clock < DRILL_FROM - 5:                 # pre-game + fast-forward to 5:00 (~35 s at 10x)
                t.insert("end", f"to 5:00 {clock(max(0, self.game_clock))}\n", "dim")
            else:
                t.insert("end", f"{clock(self.game_clock)}/{clock(DRILL_TO)}")
                if self.game_nw is not None:
                    t.insert("end", "  nw ", "dim")
                    t.insert("end", f"{self.game_nw:,}")
                t.insert("end", "\n")
        elapsed = now - self.start
        progress = done + frac_game
        eta = elapsed / progress * (total - progress) if progress > 0.2 and total and not finished else None
        t.insert("end", "  elapsed  ", "dim")
        t.insert("end", clock(elapsed) if not finished else "-")
        t.insert("end", "   eta  ", "dim")
        t.insert("end", clock(eta) if eta else "--:--")
        t.insert("end", "   done ≈ ", "dim")
        t.insert("end", (time.strftime("%H:%M", time.localtime(now + eta)) if eta else "--:--") + "\n")
        # the order games are played in (round-robin), labelled by speed: done green, now orange, to come dim
        labels = {}
        for s in setups:
            sp = self.setup_info(s)[0]
            m = re.search(r"(\d+)x$", s)
            labels[s] = sp or (m.group(1) + "x" if m else "2x")      # no game yet: from its name, else bot_batch's 2x
        if len(set(labels.values())) < len(setups):              # same speed everywhere: label by setup instead
            labels = {s: s[:4] for s in setups}
        t.insert("end", "  order   ", "dim")
        for i, s in enumerate(self.order):
            tag = "green" if i < done else "orange" if i == done and not finished else "dim"
            t.insert("end", ("▸" if tag == "orange" else " ") + labels[s], tag)
        t.insert("end", "\n")
        t.insert("end", f"  {'setup':8s} {'speed':>5s} {'games':>5s} {'nw avg':>7s} {'lh avg':>6s} {'s/game':>6s} "
                        f"{'Δ nw vs ' + (base or '')[:4]:>12s}\n", "dim")
        bnw = self.avg_nw(base) if base else None
        for s in setups:
            ok = [r for r in self.rows if r["setup"] == s and r["status"] == "ok"]
            bad = sum(1 for r in self.rows if r["setup"] == s and r["status"] != "ok")
            sp, secs = self.setup_info(s)
            t.insert("end", f"  {s[:8]:8s} ", "orange" if s == cur and not finished else "")
            t.insert("end", f"{sp or '-':>5s} ")
            t.insert("end", f"{len(ok):>5d} ")
            nw = self.avg_nw(s)
            lh = sum(float(r["lh"]) for r in ok) / len(ok) if ok else None
            t.insert("end", f"{nw:>7,.0f} " if nw is not None else f"{'-':>7s} ")
            t.insert("end", f"{lh:>6.1f} " if lh is not None else f"{'-':>6s} ")
            t.insert("end", f"{secs:>6.0f} " if secs else f"{'-':>6s} ")
            if s == base or nw is None or bnw is None:
                t.insert("end", f"{'-':>12s}", "dim")
            else:
                d = nw - bnw
                t.insert("end", f"{d:>+12,.0f}", "green" if d > 0 else "red" if d < 0 else "")
            if bad:
                t.insert("end", f"  {bad} failed", "red")
            t.insert("end", "\n")
        frac = progress / total if total else 0
        fill = int(round(frac * BAR_W))
        t.insert("end", "  ")
        t.insert("end", "█" * fill, "green")
        t.insert("end", "░" * (BAR_W - fill), "barbg")
        t.insert("end", f" {frac * 100:5.1f}%\n", "green")
        fails = sum(1 for r in self.rows if r["status"] != "ok")
        tail = f" · {fails} failed" if fails else ""
        if finished:
            status, scol = "done" + tail, "red" if fails else "green"
        elif self.status.get("stopped"):
            status, scol = "stopped", "red"
        elif self.game_wall and (self.game_clock or -1) >= 0 and now - self.game_wall > 60:
            status, scol = "stalled (game log quiet for 60 s)", "red"
        else:
            status, scol = "running" + tail, "red" if fails else "green"
        t.insert("end", "  ● ", scol)
        t.insert("end", status, scol)
        t.configure(state="disabled")
        self.root.after(1000, self.tick)


def main():
    ap = argparse.ArgumentParser(description="progress window for the March lab or a bot batch")
    ap.add_argument("path", nargs="?", help="a lab run (.jsonl) or a batch (.csv)")
    ap.add_argument("--batch", nargs="?", const="latest", help="follow a bot_batch.py batch (default: the latest)")
    ap.add_argument("--runs", type=int, default=5, help="batch: games per setup, if the batch has no status file")
    a = ap.parse_args()
    path = a.path
    if a.batch:
        path = latest_batch() if a.batch == "latest" else a.batch
    elif not path:                                                    # whichever started last
        path = max([p for p in (latest_lab(), latest_batch()) if p], key=os.path.getctime, default=None)
    if not path:
        sys.exit("no lab run or batch found in bot_runs/")
    if path.endswith(".csv"):
        BatchHud(path, a.runs).root.mainloop()
    else:
        Hud(path).root.mainloop()


if __name__ == "__main__":
    main()
