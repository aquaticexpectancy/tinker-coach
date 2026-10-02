"""Buttons + results for the stacking drill (bot.py --stack-drill opens it; top right, always on top).

    python stack_hud.py                 the latest stacking drill
    python stack_hud.py <run.jsonl>

Buttons type into Dota's console (the port bot.py opens with -netconport): Skip to :40, Auto-skip on/off,
Pause, Reset creeps, Go to (a clock like 7:40, forward only). Below: the clock and your last attempts, read live
from the drill's log. Dota must be in Borderless Window mode to see it on top. Drag to move, right-click to close.
"""
import glob
import json
import os
import sys
import tkinter as tk

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bot  # noqa: E402  (netcon)
from lab_hud import BAR_BG, BG, DIM, FG, FONT, GREEN, ORANGE, RED  # noqa: E402

BTN = {"bg": "#2b2b2b", "fg": FG, "activebackground": "#3a3a3a", "activeforeground": FG, "relief": "flat",
       "font": FONT, "padx": 8, "pady": 3, "bd": 0, "highlightthickness": 0, "cursor": "hand2"}


def latest_drill():
    runs = [p for p in glob.glob(os.path.join(HERE, "bot_runs", "*.jsonl"))
            if '"stack_drill"' in open(p, encoding="utf-8", errors="replace").read(60000)]
    return max(runs, key=os.path.getmtime) if runs else None


class StackHud:
    def __init__(self, path):
        self.path, self.pos = path, 0
        self.clock, self.station, self.boxes, self.attempts, self.auto = None, "?", 0, [], True
        root = self.root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-alpha", 0.94)
        root.configure(bg=BG, highlightthickness=1, highlightbackground="#2e2e2e")
        top = tk.Frame(root, bg=BG)
        top.pack(fill="x", padx=10, pady=(8, 4))
        self.title = tk.Label(top, text="* Stacking drill", bg=BG, fg=ORANGE, font=FONT, anchor="w")
        self.title.pack(side="left")
        self.clk = tk.Label(top, text="--:--", bg=BG, fg=FG, font=FONT)
        self.clk.pack(side="right")
        row = tk.Frame(root, bg=BG)
        row.pack(fill="x", padx=10, pady=2)
        tk.Button(row, text="Skip to :40", command=lambda: self.send("sd_skip"), **BTN).pack(side="left", padx=(0, 4))
        self.auto_btn = tk.Button(row, text="Auto-skip: on", command=self.toggle_auto, **BTN)
        self.auto_btn.pack(side="left", padx=4)
        tk.Button(row, text="Pause", command=lambda: self.send("sd_pause"), **BTN).pack(side="left", padx=4)
        row2 = tk.Frame(root, bg=BG)
        row2.pack(fill="x", padx=10, pady=2)
        tk.Button(row2, text="Reset creeps", command=lambda: self.send("sd_reset"), **BTN).pack(side="left", padx=(0, 4))
        tk.Label(row2, text="Go to", bg=BG, fg=DIM, font=FONT).pack(side="left", padx=(8, 4))
        self.goto = tk.Entry(row2, width=6, bg="#2b2b2b", fg=FG, insertbackground=FG, relief="flat", font=FONT)
        self.goto.insert(0, "7:40")
        self.goto.pack(side="left")
        self.goto.bind("<Return>", lambda e: self.send("sd_goto " + self.goto.get().strip()))
        tk.Button(row2, text="Go", command=lambda: self.send("sd_goto " + self.goto.get().strip()), **BTN).pack(side="left", padx=4)
        self.msg = tk.Label(root, text="", bg=BG, fg=DIM, font=FONT, anchor="w")
        self.msg.pack(fill="x", padx=10)
        self.text = tk.Text(root, width=56, height=7, wrap="none", bg=BG, fg=FG, font=FONT, bd=0, highlightthickness=0,
                            padx=10, pady=4, cursor="arrow")
        self.text.pack()
        for tag, col in (("orange", ORANGE), ("dim", DIM), ("green", GREEN), ("red", RED)):
            self.text.tag_configure(tag, foreground=col)
        root.update_idletasks()
        root.geometry(f"+{root.winfo_screenwidth() - root.winfo_reqwidth() - 16}+16")
        for w in (root, top, self.title, self.clk, self.msg, self.text):
            w.bind("<ButtonPress-1>", self._grab)
            w.bind("<B1-Motion>", self._drag)
            w.bind("<Button-3>", lambda e: root.destroy())
        self.tick()

    def _grab(self, e):
        self._dx, self._dy = e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def _drag(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def send(self, cmd):
        ok = bot.netcon(cmd)
        self.msg.configure(text=(f"sent: {cmd}" if ok else "Dota's console port isn't open (start with bot.py --stack-drill)"),
                           fg=DIM if ok else RED)

    def toggle_auto(self):
        self.send("sd_auto")
        self.auto = not self.auto
        self.auto_btn.configure(text=f"Auto-skip: {'on' if self.auto else 'off'}")

    def read(self):
        if not self.path:
            self.path = latest_drill()
            if not self.path:
                return
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
                    if r.get("clock") is not None:
                        self.clock = r["clock"]
                    k = r.get("kind")
                    if k == "stack_drill":
                        self.station, self.boxes = r.get("station", "?"), len(r.get("boxes", []))
                    elif k == "stack_attempt":
                        self.attempts.append(r)
        except OSError:
            pass

    def tick(self):
        self.read()
        if self.clock is not None and self.clock >= 0:
            c = self.clock
            self.clk.configure(text=f"{int(c // 60)}:{int(c % 60):02d}", fg=ORANGE if c % 60 >= 40 else FG)
        self.title.configure(text=f"* Stacking drill  {self.station} · {self.boxes} boxes")
        t = self.text
        t.configure(state="normal")
        t.delete("1.0", "end")
        ok = sum(1 for a in self.attempts if any(x.get("stacked") for x in a.get("result", [])))
        t.insert("end", f"attempts {len(self.attempts)}   stacked {ok}\n", "dim")
        for a in self.attempts[-5:][::-1]:
            m = a.get("minute", 0)
            t.insert("end", f"{m}:59  ", "dim")
            parts = [x for x in a.get("result", []) if x.get("before") or x.get("after")]
            if not parts:
                t.insert("end", "no creeps at the camps\n", "dim")
                continue
            for x in parts:
                name = x["box"].replace("neutralcamp_", "")
                if x.get("stacked"):
                    t.insert("end", f"{name} {x['before']}->{x['after']} STACKED  ", "green")
                elif x.get("blocked"):
                    why = "you" if x.get("hero_in_box") else ",".join(x.get("in_box", [])[:2])
                    t.insert("end", f"{name} blocked ({why})  ", "red")
                else:
                    t.insert("end", f"{name} {x['before']}->{x['after']}  ", "dim")
            t.insert("end", "\n")
        t.configure(state="disabled")
        self.root.after(500, self.tick)


if __name__ == "__main__":
    StackHud(sys.argv[1] if len(sys.argv) > 1 else None).root.mainloop()
