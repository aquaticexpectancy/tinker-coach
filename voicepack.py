"""Record your own voice-over for the coach's callouts.

    python voicepack.py

One row per callout: ● record, ■ stop, ▶ play, ✕ delete. Recordings are saved as
voice/<key>.wav and the coach plays them instead of the Windows voice. Uses the
Windows MCI recorder (winmm), so nothing extra to install; it records from your
default microphone.
"""
import ctypes
import pathlib
import tkinter as tk
import winsound

from engine import VOICE_LINES

HERE = pathlib.Path(__file__).parent
VOICE = HERE / "voice"
VOICE.mkdir(exist_ok=True)
winmm = ctypes.windll.winmm
BG, PANEL, FG, DIM, RED, GREEN = "#101418", "#1a2027", "#e8edf2", "#8a96a3", "#ff5a4a", "#3ecf73"

# where each line is used, so you know what tone to go for
WHEN = {
    "prekeen": "4:00+, before you have Keen", "keen": "the moment you learn Keen Teleport",
    "switch40": "40 s after Keen and still no camp", "rearm": "in fountain, not Rearmed after 3.5 s",
    "go": "in fountain for 9 s", "goC": "in fountain and the ancients are the next station",
    "lowC": "you landed at the ancients with too little mana", "ctime": "7:30 and no ancient trip yet",
    "nofarm": "40 s without a last hit", "wave": "an enemy wave is pushing your tower",
    "lowmana": "under 300 mana away from fountain (Bottle charges counted)",
}


def mci(cmd: str) -> str:
    buf = ctypes.create_unicode_buffer(256)
    err = winmm.mciSendStringW(cmd, buf, 255, None)
    if err:
        ebuf = ctypes.create_unicode_buffer(256)
        winmm.mciGetErrorStringW(err, ebuf, 255)
        raise RuntimeError(ebuf.value)
    return buf.value


class Recorder:
    def __init__(self):
        self.key = None

    def start(self, key):
        self.stop(save=False)
        mci("open new type waveaudio alias rec")
        # 16 kHz mono 16-bit: plenty for speech and tiny files
        mci("set rec bitspersample 16 channels 1 samplespersec 16000 bytespersec 32000 alignment 2")
        mci("record rec")
        self.key = key

    def stop(self, save=True):
        if not self.key:
            return None
        key, self.key = self.key, None
        try:
            mci("stop rec")
            if save:
                mci(f'save rec "{VOICE / (key + ".wav")}"')
        finally:
            mci("close rec")
        return key


def main():
    rec = Recorder()
    root = tk.Tk()
    root.title("Tinker Coach · voice-over")
    root.configure(bg=BG)
    tk.Label(root, text="Record your own callouts", font=("Segoe UI", 15, "bold"), fg=FG, bg=BG).grid(
        row=0, column=0, columnspan=6, sticky="w", padx=12, pady=(10, 0))
    tk.Label(root, text="● record  ·  ■ stop (saves)  ·  ▶ play  ·  ✕ delete (that line goes silent). Keep lines short: they play mid-fight.",
             font=("Segoe UI", 9), fg=DIM, bg=BG).grid(row=1, column=0, columnspan=6, sticky="w", padx=12, pady=(0, 8))
    status = {}

    def refresh(key):
        has = (VOICE / f"{key}.wav").exists()
        status[key].config(text="your voice" if has else "silent", fg=GREEN if has else DIM)

    def do_rec(key):
        try:
            rec.start(key)
            status[key].config(text="● recording…", fg=RED)
        except RuntimeError as e:
            status[key].config(text=f"mic error: {e}", fg=RED)

    def do_stop(key):
        if rec.key == key:
            rec.stop(save=True)
        refresh(key)

    def do_play(key):
        wav = VOICE / f"{key}.wav"
        if wav.exists():
            winsound.PlaySound(str(wav), winsound.SND_FILENAME | winsound.SND_ASYNC)
        # not recorded yet: nothing plays in game for this line either

    def do_del(key):
        (VOICE / f"{key}.wav").unlink(missing_ok=True)
        refresh(key)

    btn = dict(bg=PANEL, fg=FG, relief="flat", width=3, font=("Segoe UI", 11, "bold"), activebackground="#2a323a", activeforeground=FG)
    for i, (key, text) in enumerate(VOICE_LINES.items(), start=2):
        tk.Label(root, text=f"“{text}”", font=("Segoe UI", 11, "bold"), fg=FG, bg=BG, anchor="w", width=34).grid(row=i, column=0, sticky="w", padx=(12, 4))
        tk.Label(root, text=WHEN.get(key, ""), font=("Segoe UI", 8), fg=DIM, bg=BG, anchor="w", width=34).grid(row=i, column=1, sticky="w")
        tk.Button(root, text="●", fg=RED, command=lambda k=key: do_rec(k), **{k: v for k, v in btn.items() if k != "fg"}).grid(row=i, column=2, padx=2, pady=3)
        tk.Button(root, text="■", command=lambda k=key: do_stop(k), **btn).grid(row=i, column=3, padx=2)
        tk.Button(root, text="▶", command=lambda k=key: do_play(k), **btn).grid(row=i, column=4, padx=2)
        tk.Button(root, text="✕", command=lambda k=key: do_del(k), **btn).grid(row=i, column=5, padx=2)
        status[key] = tk.Label(root, text="", font=("Segoe UI", 9), bg=BG, width=14, anchor="w")
        status[key].grid(row=i, column=6, padx=(6, 12))
        refresh(key)
    root.protocol("WM_DELETE_WINDOW", lambda: (rec.stop(save=False), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
