"""The March lab's or a bot batch's progress in Telegram: one message, edited every 5 s (same numbers as lab_hud.py).

    python lab_tele.py              the latest lab run or batch, whichever started last
    python lab_tele.py --batch      the latest bot_batch.py batch (--lab: the latest lab run)
    python lab_tele.py <run.jsonl | batch.csv>

Setup (once): make a bot with @BotFather (/newbot), put its token in telegram_token.txt next to this file (git-
ignored) or in TELEGRAM_BOT_TOKEN, and send /start to the bot. The chat is remembered in telegram_chat.txt and
the message in telegram_msg.txt: every run edits that same message instead of sending a new one.
Stops by itself when the lab ends (the last message stays), or with Ctrl+C.
"""
import argparse
import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lab_hud  # noqa: E402  (latest_lab, short)

TOKEN_FILE, CHAT_FILE = os.path.join(HERE, "telegram_token.txt"), os.path.join(HERE, "telegram_chat.txt")
MSG_FILE = os.path.join(HERE, "telegram_msg.txt")      # the one message every run edits (sent once, then reused)
EVERY, BAR_W, WIDTH = 5, 16, 40


def api(token, method, **params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=20) as r:
        return json.loads(r.read())


def chat_id(token):
    if os.path.exists(CHAT_FILE):
        return open(CHAT_FILE).read().strip()
    print("Send /start to your bot in Telegram ...")
    while True:
        for u in api(token, "getUpdates", timeout=10).get("result", []):
            msg = u.get("message") or {}
            if msg.get("chat", {}).get("id"):
                cid = str(msg["chat"]["id"])
                open(CHAT_FILE, "w").write(cid)
                print("chat", cid)
                return cid
        time.sleep(1)


class State:
    """The lab log, read incrementally."""

    def __init__(self, path):
        self.path, self.pos, self.start, self.total, self.results, self.ended, self.queue = path, 0, None, None, [], False, None

    def read(self):
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
        if self.total and self.queue is None:
            try:
                import bot
                cfg = bot.lab_config(argparse.Namespace(lab=1, lab_stations="A,C,D,E", lab_map="creeptests", lab_probe=None))
                per = [(c, ml, n, l) for c in cfg["combos"] for ml in cfg["march_levels"] for n in cfg["marches"] for l in cfg["lasers"]]
                self.queue = per * max(1, self.total // max(1, len(per)))
            except Exception:
                self.queue = []

    def text(self):
        t = ["✻ Tinker March lab"]
        if not self.start:
            return "\n".join(t + ["  waiting for the lab to start…"])
        now, total = time.time(), self.total or 0
        done = min(len(self.results), total) if total else len(self.results)
        elapsed = now - self.start
        rate = done / elapsed if elapsed > 0 and done else 0
        eta = (total - done) / rate if rate and done < total else None
        if self.ended or (total and done >= total):
            status = "✅ done"
        elif self.results and now - self.results[-1]["wall"] > 30:
            status = "🟥 stalled (no result for 30 s)"
        else:
            status = "🟢 running"
        cur = self.queue[done] if self.queue and done < len(self.queue) else None
        if cur:
            c, ml, n, l = cur
            fam = lab_hud.short(" + ".join("+".join(sp["family"]) for sp in c["spawns"]))
            room = WIDTH - len("family   ")
            t.append(f"testing  {c['station']} · March {ml} · {n}M{('+Laser' if l == 1 else '+Laser max HP') if l else ''}")
            t.append("family   " + (fam if len(fam) <= room else fam[:room - 1] + "…"))
        else:
            t += ["testing  -", "family   -"]
        combos = len({json.dumps(q[0]) for q in self.queue}) if self.queue else 0
        per_combo = total // combos if combos else 16
        mm = lambda s: f"{int(s // 60):02d}:{int(s % 60):02d}"
        t.append(f"elapsed  {mm(elapsed)}   eta {mm(eta) if eta else '--:--'}")
        t.append(f"done ≈   {time.strftime('%H:%M', time.localtime(now + eta)) if eta else '--:--'} local")
        t.append(f"families {done // per_combo}/{combos or '?'}   tests {done}/{total}")
        frac = done / total if total else 0
        fill = int(round(frac * BAR_W))
        t.append("🟩" * fill + "⬜" * (BAR_W - fill) + f" {frac * 100:.1f}%")
        t.append(status)
        return "\n".join(t)


class BatchState:
    """A bot_batch.py batch, read through lab_hud.BatchHud (same numbers as the window), laid out for a phone."""

    def __init__(self, path):
        self.hud = lab_hud.BatchHud(path, 5, window=False)
        self.ended = False

    def read(self):
        self.hud.read()

    def text(self):
        h, now = self.hud, time.time()
        mm = lab_hud.clock
        setups = list(dict.fromkeys(h.order)) or list(dict.fromkeys(r["setup"] for r in h.rows))
        total, done = len(h.order), len(h.rows)
        self.ended = bool(h.status.get("done")) or bool(total and done >= total) or bool(h.status.get("stopped"))
        t = ["✻ Tinker bot batch", " vs ".join(setups)]
        frac_game = 0.0
        if not self.ended:
            cur = h.order[done] if done < total else "?"
            sp = f" {h.game_speed:g}x" if h.game_speed and (h.game_clock or 0) >= lab_hud.DRILL_FROM - 5 else ""
            t.append(f"game     {done + 1}/{total or '?'}  {cur}{sp}")
            gs = h.status.get("game_start")
            if h.game_clock is None:
                t.append("clock    Dota loading" + (f" {mm(now - gs)}" if gs else "…"))
            elif h.game_clock < lab_hud.DRILL_FROM - 5:
                t.append(f"clock    to 5:00 {mm(max(0, h.game_clock))}")
            else:
                t.append(f"clock    {mm(h.game_clock)}/{mm(lab_hud.DRILL_TO)}"
                         + (f"  nw {h.game_nw:,}" if h.game_nw is not None else ""))
                frac_game = min(1.0, max(0.0, (h.game_clock - lab_hud.DRILL_FROM) / (lab_hud.DRILL_TO - lab_hud.DRILL_FROM)))
        else:
            t.append(f"game     {done}/{total} played")
        elapsed = now - h.start
        progress = done + frac_game
        eta = elapsed / progress * (total - progress) if progress > 0.2 and total and not self.ended else None
        t.append(f"elapsed  {mm(elapsed)}   eta {mm(eta) if eta else '--:--'}")
        t.append(f"done ≈   {time.strftime('%H:%M', time.localtime(now + eta)) if eta else '--:--'} local")
        base = setups[0] if setups else None
        bnw = h.avg_nw(base) if base else None
        for s in setups:                                         # one line a setup: games, nw avg, vs the first
            ok = [r for r in h.rows if r["setup"] == s and r["status"] == "ok"]
            nw = h.avg_nw(s)
            lh = sum(float(r["lh"]) for r in ok) / len(ok) if ok else None
            diff = "" if s == base or nw is None or bnw is None else f" {nw - bnw:+,.0f}"
            t.append(f"{s[:11]:11s} {len(ok)}g " + (f"{nw:,.0f} {lh:.0f}lh{diff}" if nw is not None else "-"))
        fill = int(round(progress / total * BAR_W)) if total else 0
        t.append("🟩" * fill + "⬜" * (BAR_W - fill) + f" {progress / total * 100 if total else 0:.0f}%")
        fails = sum(1 for r in h.rows if r["status"] != "ok")
        if h.status.get("stopped"):
            t.append("🟥 stopped")
        elif self.ended:
            t.append("✅ done" + (f" · {fails} failed" if fails else ""))
        elif h.game_wall and (h.game_clock or -1) >= 0 and now - h.game_wall > 60:
            t.append("🟥 stalled (game log quiet for 60 s)")
        else:
            t.append(("🟢 running" if not fails else f"🟠 running · {fails} failed"))
        return "\n".join(t)


def reuse(token, cid, text):
    """Edit the message an earlier run sent; send a new one only if it's gone (deleted, or never sent)."""
    if os.path.exists(MSG_FILE):
        mid = open(MSG_FILE).read().strip()
        try:
            api(token, "editMessageText", chat_id=cid, message_id=mid, text=text, parse_mode="HTML")
            return mid
        except urllib.error.HTTPError as ex:
            if "not modified" in ex.read().decode("utf-8", "replace"):
                return mid                                  # same text as already shown: the message is there
        except Exception:
            pass
    mid = str(api(token, "sendMessage", chat_id=cid, text=text, parse_mode="HTML")["result"]["message_id"])
    open(MSG_FILE, "w").write(mid)
    return mid


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or (open(TOKEN_FILE).read().strip() if os.path.exists(TOKEN_FILE) else None)
    if not token:
        sys.exit("no bot token: put it in telegram_token.txt (see the top of this file)")
    cid = chat_id(token)
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", help="a lab run (.jsonl) or a batch (.csv)")
    ap.add_argument("--batch", action="store_true", help="the latest bot_batch.py batch")
    ap.add_argument("--lab", action="store_true", help="the latest lab run")
    a = ap.parse_args()
    path = a.path
    if not path:                                                  # default: whichever started last
        cands = [] if a.batch else [lab_hud.latest_lab()]
        cands += [] if a.lab else [lab_hud.latest_batch()]
        path = max([p for p in cands if p], key=os.path.getctime, default=None)
    if not path:
        sys.exit("no lab run or batch found in bot_runs/")
    print("following", os.path.basename(path))
    st = BatchState(path) if path.endswith(".csv") else State(path)
    st.read()
    body = lambda: "<pre>" + html.escape(st.text()) + "</pre>"
    msg = reuse(token, cid, body())
    last = None
    while True:
        time.sleep(EVERY)
        st.read()
        b = body()
        if b != last:
            try:
                api(token, "editMessageText", chat_id=cid, message_id=msg, text=b, parse_mode="HTML")
                last = b
            except Exception as ex:                    # "message is not modified", a network blip: try next time
                print("edit:", ex)
        if st.ended or (getattr(st, "total", None) and len(st.results) >= st.total):
            break


if __name__ == "__main__":
    main()
