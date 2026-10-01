"""Tinker Jev bot: a Workshop custom game where a script plays Tinker from 0:00 to 10:00 and Jev
makes the decisions (where to Keen next, how to finish a camp).

    python bot.py                    install the addon, start the bridge, launch Dota into the bot game
    python bot.py --advisor rules    same, but the built-in rules decide (for comparing with Jev)
    python bot.py --speed 2          run the game at 2x (host_timescale)
    python bot.py --end 1200         play until 20:00 instead of 10:00
    python bot.py --no-launch        only install + run the bridge (Dota already in the bot game)
    python bot.py --video            also film the screen to bot_runs/<run>.mp4 (off by default)

Close Dota first: the bot game needs Dota started with Workshop Tools (-tools).
Everything the bot sees, decides and does is recorded to bot_runs/<date_time>.jsonl, and a one-line
result per run goes to bot_runs/summary.csv. Bot runs never touch your runs.csv or score sheet.
In game, type -bot in chat to take control yourself (and -bot again to hand it back).
"""
from __future__ import annotations

import argparse
import csv
import http.server
import json
import pathlib
import subprocess
import sys
import threading
import time

import bot_hud
import jev_advisor
from workshop import DOTA, STEAM

HERE = pathlib.Path(__file__).parent
ADDON = "tinker_bot"
GAME_DIR = DOTA / "game" / "dota_addons" / ADDON
CONTENT_DIR = DOTA / "content" / "dota_addons" / ADDON
RUNS = HERE / "bot_runs"
PORT = 3040

# Stations from 44 Immortal Tinker replays (patch 7.41), Radiant coordinates:
#   land  = median Keen landing spot of their trips there
#   stand = median spot of their first March there, face = its facing (circular mean, degrees)
#   camps = the camps they cleared on those trips, plan = their usual cast sequence
#   (M March, b Bottle, R Rearm; they Keen away right after the last March and the robots finish the camp)
STATIONS = {
    "A": {"land": (-2518, -3430), "stand": (-2024, -3876), "face": 325, "plan": "walk M b R M b R M b R M",
          "camps": [(-1437, -3398), (-1231, -4171)]},               # camps 2 + 3: what its Marches cover
    "C": {"land": (-4230, -186), "stand": (-4278, 98), "face": 124, "plan": "walk M b R M b R M b R M",
          "camps": [(-3983, 937), (-4665, -61)]},
    "D": {"land": (-7269, -1158), "stand": (-7586, -1147), "face": 169, "plan": "walk M b R M b R M",
          "camps": [(-8254, -1511), (-8263, -558), (-8434, -1262)]},
    "E": {"land": (-931, -7066), "stand": (-1632, -7720), "face": 276, "plan": "walk M b R M b R M",
          "camps": [(-1532, -7626), (-486, -7695)]},
    "B": {"land": (-964, -871), "plan": "walk M b R M", "camps": []},
}
# Immortal build (March 3 / Laser 2 at 5:00); a basic skill can't pass ceil(hero level / 2)
SKILLS = ["tinker_march_of_the_machines", "tinker_laser", "tinker_march_of_the_machines", "tinker_laser",
          "tinker_march_of_the_machines", "tinker_rearm", "tinker_march_of_the_machines", "tinker_laser", "tinker_laser",
          "special_bonus_mana_reduction_10",          # level 10: the left talent (-10% mana cost)
          "tinker_rearm", "tinker_deploy_turrets", "tinker_deploy_turrets", "tinker_deploy_turrets"]


def buy_list():
    costs = json.loads((HERE / "item_costs.json").read_text(encoding="utf-8"))
    c = lambda n: int(costs.get(n, 0))
    return [
        {"name": "item_branches", "cost": c("item_branches")}, {"name": "item_branches", "cost": c("item_branches")},
        {"name": "item_branches", "cost": c("item_branches")}, {"name": "item_tango", "cost": c("item_tango")},
        {"name": "item_faerie_fire", "cost": c("item_faerie_fire")},
        {"name": "item_bottle", "cost": c("item_bottle")},
        {"name": "item_robe", "cost": c("item_robe")},
        {"name": "item_staff_of_wizardry", "cost": c("item_staff_of_wizardry")},
        {"name": "item_kaya", "cost": c("item_recipe_kaya"), "consumes": ["item_robe", "item_staff_of_wizardry"]},
        {"name": "item_blink", "cost": c("item_blink")},
    ]


def lua(v, ind=1):
    t = "\t" * ind
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, (list, tuple)):
        return "{" + ", ".join(lua(x, ind + 1) for x in v) + "}"
    if isinstance(v, dict):
        return "{\n" + "".join(f"{t}[{json.dumps(str(k)) if not isinstance(k, int) else k}] = {lua(x, ind + 1)},\n"
                               for k, x in v.items()) + "\t" * (ind - 1) + "}"
    raise TypeError(v)


DRILL_DEFAULT = "2026-09-29_1851"      # your best F11 drill run so far: +3,000 from 5:00 to 10:00


def drill_state(session: str) -> dict:
    """Your level, skills, items and gold at 5:00 from a recorded F11 drill session."""
    import workshop
    st = workshop.state_from_session(str(HERE / "sessions" / f"{session}.jsonl"))
    if not st:
        sys.exit(f"no 5:00 state in session {session}")
    st["items"] = [i for i in st["items"] if i not in ("item_ward_observer", "item_ward_sentry")]
    st["abilities"] = {k: v for k, v in st["abilities"].items() if k != "tinker_eureka"}
    st.update(start_at=300, ffwd_speed=10, session=session)
    return st


def install(advisor: str, speed: float, end_at: int, lane_speed: float = 1.0, drill: dict | None = None,
            route: str = "rules", manual: bool = False, aim: str = "off", use_mana: bool = False,
            ready: str = "fresh", router: str = "rules") -> pathlib.Path:
    vs = GAME_DIR / "scripts" / "vscripts"
    vs.mkdir(parents=True, exist_ok=True)
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)      # the tools only list addons that have a content folder
    (GAME_DIR / "addoninfo.txt").write_text('"AddonInfo"\n{\n\t"maps"\t\t\t"dota"\n\t"IsPlayable"\t"1"\n}\n', encoding="utf-8")
    (vs / "addon_game_mode.lua").write_text((HERE / "bot_lua" / "addon_game_mode.lua").read_text(encoding="utf-8"), encoding="utf-8")
    cfg = {
        "advisor": advisor, "speed": speed, "lane_speed": lane_speed, "end_at": end_at, "pregame": 30,
        "bridge": f"http://127.0.0.1:{PORT}", "decide_timeout": 1.5, "home_reserve": 180,
        "laser_dmg": {1: 75, 2: 150, 3: 225, 4: 300},
        "stations": {k: {**{a: (list(b) if isinstance(b, tuple) else b) for a, b in v.items() if a != "camps"},
                         "camps": [list(c) for c in v["camps"]]} for k, v in STATIONS.items()},
        "lane_spot": [-900, -800], "t1_mid": [-1550, -1350], "t2_mid": [-3500, -2750], "fountain": [-6950, -6450], "station_by_rules": route != "jev", "manual": manual, "wave_min_creeps": 4,
        # Immortal March counts (neutral-HP replays): after N Marches, March again only if more HP than this is left
        # fitted on 1,098 Immortal camp trips (148 games): camp HP still standing ~6 s after the 1st March
        "more_march_hp": {"A": {2: 5500, 3: 6500}, "D": {2: 6300, 3: 8900}, "C": {2: 1100, 3: 7500}, "E": {2: 5500, 3: 8900}},
        "leave_at_once": True, "stack": False,        # stacking: off until it has a stricter rule (tested: -400)
        # stations whose Marches aim at the creeps instead of the replay facing (off: the facing everywhere)
        "aim_stations": {"C": True, "D": True, "E": True} if aim == "on" else {"D": True} if aim == "d" else {},
        # March on while the mana covers it instead of stopping at the Immortal HP thresholds (more_march_hp)
        "use_mana": use_mana,
        # fresh: a camp is ready by the creeps beyond what the last trip left; old: by all creeps there
        "ready": ready,
        # rate: go where the measured gold per second is highest (bot_lua RateRoute); rules: the Immortal routing
        "router": router,
        "skill_order": {i + 1: s for i, s in enumerate(SKILLS) if s},
        "buy": buy_list(),
    }
    if drill:
        cfg["drill"] = drill
        owned = list(drill["items"])
        rest = []
        for it in cfg["buy"]:                          # keep buying where your 5:00 inventory leaves off
            if it["name"] in owned:
                owned.remove(it["name"])
            elif it["name"] in ("item_branches", "item_tango", "item_faerie_fire"):
                continue
            else:
                rest.append(it)
        cfg["buy"] = rest
    (vs / "bot_config.lua").write_text("-- written by tinker_coach/bot.py\nreturn " + lua(cfg) + "\n", encoding="utf-8")
    return GAME_DIR


# ---------------------------------------------------------------------- Jev questions
# Jev's station guidance for the bot: the coach's Immortal lines, but the bot's own numbers on waves. Batch
# 2026-09-30 (20 runs): Jev took 0-2 wave trips a game vs the rules' 3-6, and more wave trips went with more
# net worth (r = 0.49); a wave of 4-7 creeps paid 3 kills in ~9 s, about what a camp trip pays per second.
BOT_GUIDANCE = [g for g in jev_advisor.GUIDANCE if not g.startswith("The mid wave is worth it")] + [
    "For this bot (20 test games): a mid-wave trip with 4+ creeps pays about 3 kills in ~9 s and a camp trip "
    "about 4 kills in 11-15 s, so per second a wave is as good as a camp. After a camp trip, take a visible mid "
    "wave of 4+ creeps; never two waves in a row.",
]

FINISH_TEXT = {
    "keen_now": "Leave now: the robots keep hitting during the 3 s Keen channel and their kills still count",
    "laser": "Laser a creep: one it kills (`laser.creeps_it_kills`), else the tankiest one (`tanky_creeps`), which "
             "the robots take longest on",
    "rearm_laser": "Rearm to get Laser back and Laser again: when a tanky creep is still alive after a Laser",
    "rearm_march": "One more Rearm + March: when 3+ creeps with a lot of HP are left, or creeps are expected in the "
                   "camp but not visible",
}


NAME = {"A": "mid pair (A)", "B": "mid wave", "C": "hard + ancients (C)", "D": "top-side camps (D)", "E": "far camps (E)",
        "F": "fountain", "keen_now": "leave now", "laser": "Laser", "attack": "right-click", "rearm_march": "Rearm + March",
        "rearm_laser": "Rearm + Laser"}
GOOD_COL, WARN_COL, SOFT_COL = (62, 207, 115), (255, 192, 67), (190, 199, 208)


class Bridge:
    def __init__(self, advisor: str):
        self.advisor = advisor
        RUNS.mkdir(exist_ok=True)
        self.path = RUNS / time.strftime("%Y-%m-%d_%H%M.jsonl")
        self.fh = open(self.path, "a", encoding="utf-8")
        self.lock = threading.Lock()
        self.client = None
        if advisor == "jev" and jev_advisor.api_key():
            from typesafe_sdk import TypeSafeClient
            self.client = TypeSafeClient(api_key=jev_advisor.api_key(), model="jev-latest", timeout=1.2)
        self.decisions = {"jev": 0, "rules": 0, "agree": 0}
        self.done = threading.Event()
        self.last_snap = None
        self.hud = {"advisor": advisor, "clock": None, "now": "Waiting for the game…", "trips": []}

    def write(self, rec):
        rec.setdefault("wall", time.time())
        with self.lock:
            self.fh.write(json.dumps(rec) + "\n")
            self.fh.flush()

    def log(self, rec):
        self.write(rec)
        k = rec.get("kind")
        self._hud_event(k, rec)
        if k == "snap":
            self.last_snap = rec
        elif k in ("keen", "trip", "decision", "buy", "phase", "keen_failed", "error", "toggle"):
            print(f"{int(rec.get('clock', 0)) // 60}:{int(rec.get('clock', 0)) % 60:02d}  {k:9s} "
                  + " ".join(f"{a}={b}" for a, b in rec.items() if a not in ("kind", "clock", "wall", "options")))
        if k == "end":
            self.summary(rec)
            self.done.set()

    # ------------------------------------------------------------------ what the thinking panel shows
    def _hud_event(self, k, r):
        h = self.hud
        if r.get("clock") is not None:
            h["clock"] = r["clock"]
        now = None
        if k == "snap":
            h["nw"], h["lh"] = r.get("nw"), r.get("lh")
            if r.get("phase") == "lane" and not h.get("laned"):
                now, h["now_icon"], h["now_sub"] = "Laning: last hits until level 6", "laser", "Code times every last hit (HP vs damage and armour)"
                h["laned"] = True
        elif k == "last_hit_try":
            unit = r.get("unit", "").replace("npc_dota_creep_", "").replace("_", " ")
            now, h["now_icon"], h["now_sub"] = f"Last hit: {unit}", None, f"{r.get('hp')} HP left, one attack kills it"
        elif k == "keen":
            now, h["now_icon"], h["now_sub"] = f"Keen → {NAME.get(r['to'], r['to'])}", "keen", f"{r.get('mana')} mana · 3 s channel"
        elif k == "landed":
            now, h["now_icon"], h["now_sub"] = f"Landed: {NAME.get(r['station'], r['station'])}", "keen", f"{r.get('mana')} mana"
        elif k == "cast":
            ab = r.get("ability")
            if ab == "march":
                how = {180: "turned 180° from the last one", 45: "diagonal across the lane"}.get(r.get("turn"), "straight at the creeps")
                now, h["now_icon"], h["now_sub"] = "March of the Machines", "march", how
            elif ab == "rearm":
                now, h["now_icon"], h["now_sub"] = "Rearm", "rearm", r.get("why") or "refresh March for the next one"
            elif ab == "laser":
                now, h["now_icon"], h["now_sub"] = "Laser", "laser", (r.get("unit") or "").replace("npc_dota_", "").replace("_", " ")
        elif k == "buy":
            item = r["item"].replace("item_", "").replace("_", " ").title()
            now, h["now_icon"], h["now_sub"] = f"Bought {item}", None, f"{r.get('cost')} gold"
        elif k == "phase":
            now, h["now_icon"], h["now_sub"] = "Level 6: jungle time", "keen", r.get("reason")
        elif k == "trip":
            h["trips"] = h["trips"] + [{"station": r["station"], "last_hits": r.get("last_hits", 0)}]
        elif k == "keen_failed":
            now, h["now_icon"], h["now_sub"] = f"Keen to {r.get('station')} failed", None, "skipping that spot this minute"
        elif k == "decision" and h.get("decision") and h["decision"].get("q") == r.get("what"):
            dec = h["decision"]
            dec["pick"] = r["pick"]
            if r.get("src") == "jev":
                same = r["pick"] == r["rules"]
                text = f"Jev picked {NAME.get(r['pick'], r['pick'])}" + ("" if same else f" · the rules would have picked {NAME.get(r['rules'], r['rules'])}")
                dec["verdict"] = (text, GOOD_COL if same else WARN_COL)
            else:
                why = {"timeout": "Jev too slow", "rules_lowconf": "Jev unsure", "rules": "Rules only"}.get(r.get("src"), r.get("src"))
                dec["verdict"] = (f"{why} → rules: {NAME.get(r['pick'], r['pick'])}", SOFT_COL)
        elif k == "end":
            h["end"] = f"{int(r.get('clock', 0)) // 60}:00 · net worth {r.get('nw') or 0:,} · {r.get('lh') or 0} last hits"
            now, h["now_icon"], h["now_sub"] = "Run over", None, None
        if now:
            h["now"] = now

    def _hud_decision(self, kind, state, options, rules, info):
        probs = (info or {}).get("probs") or {}
        bars = sorted(((o, probs.get(o)) for o in options), key=lambda t: -(t[1] or 0))
        if kind == "station":
            t = state.get("tinker", {})
            ready = [k for k, v in state.get("camps", {}).items() if v.get("ready")]
            wave = state.get("mid_wave", {})
            last = (state.get("last_trips") or [None])[-1]
            wtxt = (f"{wave.get('creeps')} creeps" + (", pushing your tower" if wave.get("pushing_into_your_tower") else "")) \
                if wave.get("visible") else "not on your half"
            facts = [f"Mana {t.get('mana')}/{t.get('max_mana')} · March lvl {t.get('march_level')} · Laser lvl {t.get('laser_level')}",
                     f"Camps up: {', '.join(ready) or 'none'} · respawn in {state.get('seconds_until_camps_respawn')} s",
                     f"Mid wave: {wtxt}"]
            if last:
                facts.append(f"Last trip: {last['to']} +{last['last_hits']} LH in {last['seconds']} s")
            title = "Decision · where next?"
        else:
            las = state.get("laser", {})
            facts = [f"{state.get('creeps_left_count')} creeps left, {state.get('creeps_left_total_hp') or 0:,} HP · "
                     f"robots still running {state.get('robots_still_running_seconds')} s",
                     f"Laser {las.get('damage')} dmg, {'ready' if las.get('ready') else 'on cooldown'}",
                     f"Mana after Rearm + March + Keen: {state.get('mana_after_rearm_march_and_keen')} (keep {state.get('keep_for_home')})"]
            title = "Decision · finish the camp?"
        meta = f"Jev · {info['latency_s']:.2f} s · confidence {info['confidence']:.2f}" if info else "rules"
        pick = bars[0][0] if info else rules
        self.hud["decision"] = {"q": kind, "title": title, "meta": meta, "bars": bars, "pick": pick, "rules": rules,
                                "facts": facts, "verdict": ("Thinking…", SOFT_COL)}

    def decide(self, req):
        kind, state, options, rules = req["kind"], req["state"], req["options"], req["rules"]
        if req.get("rules_only") or not self.client:
            self._hud_decision(kind, state, options, rules, None)
            return rules, "rules", None
        from typesafe_sdk import Choice, Noul
        if kind == "station":
            state = dict(state, guidance=BOT_GUIDANCE)
            q = {"pick": Choice(
                    instructions="Tinker is farming the jungle in Dota 2, Keen Teleporting to a spot, clearing it with "
                                 "March of the Machines and Rearm, and going back to fountain for mana. Using `tinker`, "
                                 "`camps`, `mid_wave`, `last_trips` and `guidance`, where should Tinker Keen to next to "
                                 "earn the most gold over the next minute?",
                    criteria={o: jev_advisor.OPTION_TEXT[o] for o in options}),
                 "stack": Noul(instructions="On this trip, is it worth pulling a camp at :53 so that it stacks, given "
                                            "`tinker` and `game_clock`?")}
        else:
            q = {"pick": Choice(
                    instructions="Tinker has done its planned Marches on a camp in Dota 2 and `creeps_left` are still "
                                 "alive. A camp with creeps left in it does not respawn at :00, so leftovers cost the "
                                 "next spawn too. What should Tinker do next, given `creeps_left`, `laser`, "
                                 "`attack_damage`, `mana_after_rearm_march_and_keen` and `keep_for_home`?",
                    criteria={o: FINISH_TEXT[o] for o in options})}
        t0 = time.time()
        try:
            r = self.client.system_one(state=state, questions=q)
        except Exception as ex:
            print("Jev failed:", type(ex).__name__, ex)
            self._hud_decision(kind, state, options, rules, None)
            return rules, "rules", None
        ch = r.choices["pick"]
        info = {"probs": dict(ch.probabilities), "confidence": ch.confidence, "latency_s": round(time.time() - t0, 2),
                "stack": r.nouls["stack"].noul if "stack" in r.nouls else None, "tokens": r.usage.input_tokens}
        self._hud_decision(kind, req["state"], options, rules, info)
        self.write({"kind": "jev", "question": kind, "state": state, "options": options, "rules": rules,
                    "pick": ch.choice, **info})
        if ch.confidence < jev_advisor.MIN_CONFIDENCE:
            return rules, "rules_lowconf", info
        return ch.choice, "jev", info

    def summary(self, end):
        snap = self.last_snap or {}
        trips = []
        decisions = []
        for line in open(self.path, encoding="utf-8"):
            r = json.loads(line)
            if r.get("kind") == "trip":
                trips.append(r)
            elif r.get("kind") == "decision":
                decisions.append(r)
        n5 = None
        for line in open(self.path, encoding="utf-8"):
            r = json.loads(line)
            if r.get("kind") == "snap" and r.get("clock", 0) >= 300:
                n5 = r
                break
        row = {"run": self.path.stem, "advisor": self.advisor, "end_clock": int(end.get("clock", 0)),
               "nw_end": end.get("nw"), "lh_end": end.get("lh"), "level_end": end.get("level"),
               "nw_5": n5 and n5.get("nw"), "lh_5": n5 and n5.get("lh"),
               "camp_trips": sum(t["station"] in ("A", "C", "D") for t in trips),
               "wave_trips": sum(t["station"] == "B" for t in trips),
               "jev_decisions": sum(d.get("src") == "jev" for d in decisions),
               "jev_differs_from_rules": sum(d.get("src") == "jev" and d.get("pick") != d.get("rules") for d in decisions)}
        new = not (RUNS / "summary.csv").exists()
        with open(RUNS / "summary.csv", "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(row))
            if new:
                w.writeheader()
            w.writerow(row)
        print("\n=== bot run over ===")
        for k, v in row.items():
            print(f"  {k:24s} {v}")
        if n5 and end.get("nw"):
            mine = your_drill_runs()
            if mine:
                earned = end["nw"] - n5["nw"]
                vals = sorted(e for _, e in mine)
                print(f"  earned 5:00 -> end       {earned:,}   (your F11 drills: {vals[0]:,} to {vals[-1]:,})")
        print(f"  recording: {self.path}")


def your_drill_runs() -> list:
    """(session, net worth earned 5:00 -> 10:00) of your F11 drill runs (0 last hits at 5:00, fair 5:00 gold)."""
    runs = HERE / "runs.csv"
    if not runs.exists():
        return []
    by = {}
    for r in csv.DictReader(open(runs, encoding="utf-8")):
        if r["minute"] in ("5", "10") and r.get("net_worth"):
            by.setdefault(r["session"], {})[r["minute"]] = (int(r["lh"] or 0), int(r["net_worth"]))
    return [(s, v["10"][1] - v["5"][1]) for s, v in by.items()
            if "5" in v and "10" in v and v["5"][0] == 0 and 2000 <= v["5"][1] <= 2600]


def serve(bridge: Bridge):
    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                req = json.loads(body or b"{}")
            except ValueError:
                req = {}
            out = b"ok"
            if self.path == "/log":
                bridge.log(req)
            elif self.path == "/decide":
                pick, src, info = bridge.decide(req)
                p = (info or {}).get("probs", {}).get(pick)
                out = f"pick={pick};src={src};prob={p if p is not None else ''}".encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def dota_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq dota2.exe"], capture_output=True, text=True).stdout
    return "dota2.exe" in out.lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--advisor", choices=["jev", "rules"], default="rules", help="rules (default, no Jev calls) or jev")
    ap.add_argument("--speed", type=float, default=1.0, help="game speed once the jungle starts")
    ap.add_argument("--lane-speed", type=float, default=None, help="game speed while laning (default: --speed)")
    ap.add_argument("--end", type=int, default=600, help="game clock (s) when the run ends")
    ap.add_argument("--no-launch", action="store_true")
    ap.add_argument("--route", choices=["rules", "jev"], default="rules", help="who decides where to Keen next")
    ap.add_argument("--manual", action="store_true", help="you play: the drill sets up 5:00, no bot, no video; the coach guides")
    ap.add_argument("--drill", nargs="?", const=DRILL_DEFAULT, default=None, metavar="SESSION",
                    help="skip the lane: start at 5:00 in fountain from your saved F11 drill state "
                         f"(default: your best F11 run, session {DRILL_DEFAULT})")
    ap.add_argument("--video", action="store_true", help="film the screen to bot_runs/<run>.mp4 (~300 MB a run)")
    ap.add_argument("--no-video", action="store_true", help="(the default now; kept so old commands still work)")
    ap.add_argument("--aim", choices=["on", "off", "d"], default="off",
                    help="on: Marches at C/D/E aim at the creeps; d: at D only; off: the Immortal replay facing")
    ap.add_argument("--marches", choices=["immortal", "mana"], default="mana",
                    help="immortal: stop at the Immortal HP thresholds; mana: March on while the mana covers it")
    ap.add_argument("--router", choices=["rules", "rate"], default="rate",
                    help="rules: the Immortal routing rules; rate: the best measured gold per second")
    ap.add_argument("--ready", choices=["fresh", "old"], default="fresh",
                    help="fresh: leftovers from the last trip don't make a camp ready; old: every creep counts")
    a = ap.parse_args()
    if subprocess.run([sys.executable, str(HERE / "lua_check.py")]).returncode != 0:
        sys.exit("bot script check failed: not launching")
    drill = drill_state(a.drill) if a.drill else None
    if drill:
        print(f"Drill start: your {a.drill} state at 5:00: level {drill['level']}, {drill['abilities']}, "
              f"{drill['items']}, {drill['gold']} gold")
    if a.manual:
        a.advisor, a.no_video = "rules", True
        (HERE / "manual_drill.flag").write_text("1")          # the coach logs this run as yours
    else:
        (HERE / "manual_drill.flag").unlink(missing_ok=True)
    print("Addon written to", install(a.advisor, a.speed, a.end, a.lane_speed or a.speed, drill, a.route, manual=a.manual,
                                      aim=a.aim, use_mana=a.marches == "mana", ready=a.ready, router=a.router))
    print("Route decided by:", a.route)
    bot_hud.COMPARE_SESSION = a.drill
    bridge = Bridge(a.advisor)
    try:
        serve(bridge)
    except OSError as ex:
        sys.exit(f"Bridge port {PORT} is busy (another bot.py running?): {ex}")
    print(f"Bridge on 127.0.0.1:{PORT}, advisor = {a.advisor}, recording to {bridge.path}")
    if not a.no_launch:
        if dota_running():
            sys.exit("Dota is running: close it first (the bot game needs Dota started with Workshop Tools).")
        subprocess.Popen([str(STEAM / "steam.exe"), "-applaunch", "570", "-tools", "-addon", ADDON, "-novid",
                          "-gamestateintegration", "-condebug", "-language", "english", "+dota_launch_custom_game", ADDON, "dota"])
        print("Launching Dota (Workshop Tools) into the bot game… the first load takes a minute.")
    print("Type -bot in the game chat to take over. Ctrl+C here to stop.\n")
    if a.manual:
        print("Manual drill: you play from 5:00. The coach's HUD guides you. Ctrl+C here after 10:00.")
        try:
            while not bridge.done.wait(1):
                pass
        except KeyboardInterrupt:
            pass
        (HERE / "manual_drill.flag").unlink(missing_ok=True)
        return
    run_ui(bridge, record=a.video and not a.no_video)


def run_ui(bridge: Bridge, record: bool):
    """Thinking panel on screen + whole-screen recording from the start of the game to the end card."""
    import ctypes
    import tkinter as tk
    import bot_hud
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    sw, sh = ctypes.windll.user32.GetSystemMetrics(0), ctypes.windll.user32.GetSystemMetrics(1)
    root = tk.Tk()
    root.withdraw()
    hud = bot_hud.BotHud(root, sw, sh)
    rec = bot_hud.Recorder(bridge.path.with_suffix(".mp4")) if record else None
    st = {"recording": False, "end_at": None}

    def tick():
        h = dict(bridge.hud)
        try:
            hud.render(h)
        except Exception as ex:
            print("HUD:", ex)
        if rec and not st["recording"] and h.get("clock") is not None and h["clock"] >= -5:
            st["recording"] = True
            threading.Thread(target=rec.start, daemon=True).start()
        if bridge.done.is_set() and st["end_at"] is None:
            st["end_at"] = time.time() + 6                    # keep the result card on screen (and on video) for 6 s
        if st["end_at"] and time.time() >= st["end_at"]:
            if rec:
                rec.stop()
            root.destroy()
            return
        root.after(150, tick)

    root.after(150, tick)
    try:
        root.mainloop()
    except KeyboardInterrupt:
        if rec:
            rec.stop()


if __name__ == "__main__":
    main()
