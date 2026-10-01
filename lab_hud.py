"""A small CLI-style progress window for the March lab (top right, always on top). Reads the lab's log live.

    python lab_hud.py              the latest lab run
    python lab_hud.py <run.jsonl>

Shows the family mix being tested now, time passed, ETA, families (combos) checked, tests done and a progress bar.
Drag it with the left mouse button, right-click to close. Dota must be in Borderless Window mode to see it on top.
"""
import argparse
import glob
import json
import os
import sys
import time
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# Claude Code colours (dark theme)
BG, FG, DIM, ORANGE, GREEN, RED, BAR_BG = "#1a1a1a", "#e8e6e3", "#8b8b8b", "#d97757", "#4eba65", "#e5534b", "#3a3a3a"
FONT = ("Cascadia Mono", 10)
BAR_W = 28


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


class Hud:
    def __init__(self, path):
        self.path, self.pos, self.start, self.total, self.results, self.ended = path, 0, None, None, [], False
        self.queue = None
        self.root = root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.94)
        root.configure(bg=BG)
        self.text = tk.Text(root, width=56, height=8, bg=BG, fg=FG, font=FONT, bd=0, highlightthickness=1,
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
            cfg = bot.lab_config(argparse.Namespace(lab=1, lab_stations="A,C,D,E"))
        except Exception:
            return None
        per = [(c, ml, n, l) for c in cfg["combos"] for ml in cfg["march_levels"] for n in cfg["marches"] for l in cfg["lasers"]]
        reps = max(1, (self.total or len(per)) // max(1, len(per)))
        return per * reps

    def tick(self):
        self.read()
        if self.total and self.queue is None:
            self.queue = self.build_queue() or []
        done, total = len(self.results), self.total or 0
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
            eta = (total - done) / rate if rate else None
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
                t.insert("end", f"{c['station']} · March {ml} · {n}M{'+Laser' if l else ''}\n")
                t.insert("end", "  family   ", "dim")
                t.insert("end", short(fams)[:58] + "\n")
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


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else latest_lab()
    if not path:
        sys.exit("no lab run found in bot_runs/")
    Hud(path).root.mainloop()


if __name__ == "__main__":
    main()
