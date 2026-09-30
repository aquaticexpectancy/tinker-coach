"""Tinker transition coach: turns Dota GSI payloads into tips.

Pure logic, no UI. Feed it GSI JSON dicts with Engine.update(); read Engine.view()
for everything the UI shows. Rules come from the Tinker farming study (25 parsed
patch-7.41 replays): see coach_data.json for the camp stations and benchmarks.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import statistics
import time
from dataclasses import dataclass, field
from typing import Optional

DATA = json.loads((pathlib.Path(__file__).parent / "coach_data.json").read_text(encoding="utf-8"))
TARGET = DATA["targets"]
_IC = pathlib.Path(__file__).parent / "item_costs.json"
ITEM_COSTS = json.loads(_IC.read_text(encoding="utf-8")) if _IC.exists() else {}
BOTTLE_MANA = ITEM_COSTS.get("__bottle_mana_restore", 60)   # per charge, from your Dota's items.txt
NW_SLOTS = ("slot", "stash")
_NS = pathlib.Path(__file__).parent / "neutrals.json"
NEUTRAL_STATS = json.loads(_NS.read_text(encoding="utf-8")) if _NS.exists() else {}
LASER_DMG = (0, 75, 150, 225, 300)                 # pure, from npc_dota_hero_tinker.txt
MARCH_ROBOT_DMG = (0, 13, 22, 31, 40)              # per robot, magic
MARCH_WORK_S = 4.0
# Immortal Tinkers come home with ~226 mana (median of 23 games; the best farmers ~310), enough to Rearm
# the moment they land. Coming home empty goes with less farm (r = +0.48 vs net worth gained 5-10).
KEEP_MANA = 200            # the median (226) is not a floor: a strict 250 made full 3-March clears impossible
MARCH_COST = (0, 100, 120, 140, 160)
REARM_COST = (0, 100, 150, 200)                                  # most robots have hit ~4 s after the cast      # inventory + backpack + stash count; neutral items and TP slot don't

STATION_NAMES = {
    "F": "Fountain", "A": "Mid pair", "B": "Mid wave", "C": "Hard + ancient",
    "D": "Top-lane side camps", "E": "Far camps", "lane": "Side lane", "jungle": "Jungle / river",
    "enemy": "ENEMY side", "W": "Side-lane wave",
}
# Every spoken callout. Record your own version of any line with voicepack.py
# (saved as voice/<key>.wav); lines without a recording use the Windows voice.
VOICE_LINES = {
    "prekeen": "Keen soon. Shove the wave.",
    "keen": "Keen is up. Push, go home, Rearm, camp A.",
    "switch40": "Forty seconds since Keen. Camp now.",
    "rearm": "Rearm.",
    "go": "Go.",
    "goC": "Next: ancients.",
    "lowC": "Too little mana for the ancients.",
    "ctime": "Go ancient from fountain.",
    "nofarm": "Forty seconds without a creep.",
    "wave": "Wave at your tower.",
    "lowmana": "Low mana. Keen home.",
}
# Your towers in Radiant view (Dire is mirrored), used to judge how far a wave has pushed.
T1 = {"top": (-6200, 1900), "mid": (-1550, -1350), "bot": (4950, -6100)}
T2 = {"top": (-6150, -900), "mid": (-3500, -2750), "bot": (-400, -6200)}
C_MIN_MARCH = 4            # March below level 4 doesn't kill hard/ancient camps in 3 casts
# Dire players get the same letters mirrored, so the names stay generic.
CAMP_STATIONS = ("A", "C", "D", "E")
TELEPORT_JUMP = 1600          # position jump that can only be a teleport (Blink is <= 1200)
STATION_RADIUS = 1150
LOW_MANA = 300
CAMP_MIN_LH = 3
REARM_MANA_DROP = 60      # Rearm costs 100+ mana; nothing else you cast in fountain does


def fmt(t: Optional[float]) -> str:
    if t is None:
        return "—"
    s = "-" if t < 0 else ""
    t = abs(t)
    return f"{s}{int(t // 60)}:{int(t % 60):02d}"


@dataclass
class Trip:
    start: float                 # game clock at landing
    dest: str                    # station letter / lane / jungle / enemy
    lh_start: int
    mana_start: float
    end: Optional[float] = None
    lh_gain: int = 0
    camp_lh: int = 0             # last hits gained while standing at a camp station
    marches: int = 0
    rearm_at: Optional[float] = None   # fountain only: clock when Rearm finished
    rearm_start: Optional[float] = None  # fountain only: clock when Rearm was cast (mana drop)
    spoke_idle: bool = False
    seq: list = field(default_factory=list)   # what you pressed here: M(arch) R(earm) L(aser)

    @property
    def length(self) -> Optional[float]:
        return None if self.end is None else self.end - self.start


@dataclass
class Tip:
    text: str
    level: str = "info"          # info | good | warn | bad
    speak: Optional[str] = None
    key: str = ""
    until: float = 0.0           # one-off notes expire at this game clock


class Engine:
    def __init__(self):
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self):
        self.connected_at = None
        self.last_payload_wall = 0.0
        self.game_state = ""
        self.hero_name = ""
        self.team = "radiant"
        self.clock = None
        self.alive = True
        self.level = 0
        self.mana = 0.0
        self.max_mana = 1.0
        self.lh = 0
        self.lh_seen = False
        self.pos = None                     # real world coords
        self.rv = None                       # radiant-view coords
        self.loc = "?"
        self.keen_level = 0
        self.keen_learned_at = None
        self.keen_cd = 0.0
        self.march_cd = 0.0
        self.march_level = 0
        self.laser_cd = 0.0
        self.steamid = None
        self.drill_note = None            # set by the drill watcher while fast-forwarding
        self.gold = 0
        self.gpm = 0
        self.xpm = 0
        self.net_worth = None             # gold + item costs (None until items are seen)
        self.items: list[str] = []
        self.bottle_charges = 0
        self.minute_log: list[dict] = []  # one row per game minute, for runs.csv
        self.enemy_creeps: list = []      # [(radiant-view x, y)] from the GSI minimap block
        self.neutrals: list = []          # [(unitname, real x, real y)] neutrals your minimap sees
        self.laser_level = 0
        self.laser_ready = True
        self.last_march_at = None
        self.creeps_seen_at = None
        self.waves: list = []
        self.wave_target = None           # real coords of the wave we're sending you to
        self.has_blink = False
        self.trips: list[Trip] = []
        self.last_lh_change = None
        self.first_camp_kill = None
        self.first_C_trip = None
        self.first_C_trip_mana = None
        self.first_C_kill = None
        self.last_farmed_minute = {k: -1 for k in CAMP_STATIONS}
        self.tips: list[Tip] = []
        self.spoken: set[str] = set()
        self.speech_queue: list[tuple[str, str]] = []   # (sound key, text)
        self.summary_written = False
        self.game_id = None
        self.bot_run = False
        self.advisor = getattr(self, "advisor", None)   # JevAdvisor, survives reset()

    # ------------------------------------------------------------------ helpers
    def _radiant_view(self, x, y):
        return (x, y) if self.team == "radiant" else (-x, -y)

    def _classify(self, x, y) -> str:
        bx = DATA["base_box"]
        if x < bx["x_max"] and y < bx["y_max"]:
            return "F"
        best, bd = None, 1e9
        for st, camps in DATA["stations"].items():
            for c in camps:
                d = math.hypot(c["x"] - x, c["y"] - y)
                if d < bd:
                    best, bd = st, d
        if bd < STATION_RADIUS:
            return best
        if x + y > 1200 and not (abs(x - y) < 1600 and x + y < 4000):
            return "enemy"
        if abs(x - y) < 1600:
            return "B"
        if x < -5000 or y > 5200 or x > 5000 or y < -5200:
            return "lane"
        return "jungle"

    def _say(self, key, sound, text=None):
        """key de-duplicates (one callout per event); sound picks the voice line."""
        if key not in self.spoken:
            self.spoken.add(key)
            self.speech_queue.append((sound, text or VOICE_LINES.get(sound, sound)))

    @property
    def eff_mana(self) -> float:
        """Mana you can actually use: current mana + what your Bottle charges will give back."""
        return min(self.max_mana, self.mana + self.bottle_charges * BOTTLE_MANA)

    def minute(self):
        return int((self.clock or 0) // 60)

    # ------------------------------------------------------------------ update
    def update(self, p: dict, wall: Optional[float] = None):
        wall = wall or time.time()
        self.last_payload_wall = wall
        if self.connected_at is None:
            self.connected_at = wall
        m = p.get("map") or {}
        mid = m.get("matchid")
        if mid and self.game_id and mid != self.game_id:
            self.reset()
            self.connected_at = wall
        if mid:
            self.game_id = mid
        self.game_state = m.get("game_state", self.game_state)
        self.bot_run = "tinker_bot" in str(m.get("customgamename") or "") and not os.path.exists(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "manual_drill.flag"))   # the bot map, unless you're playing it
        if "clock_time" in m:
            self.clock = float(m["clock_time"])
        pl = p.get("player") or {}
        if pl.get("team_name") in ("radiant", "dire"):
            self.team = pl["team_name"]
        self.steamid = pl.get("steamid", self.steamid)
        self.gold = int(pl.get("gold", self.gold) or 0)
        self.gpm = int(pl.get("gpm", self.gpm) or 0)
        self.xpm = int(pl.get("xpm", self.xpm) or 0)
        mm = p.get("minimap")
        if isinstance(mm, dict):
            my_team = 2 if self.team == "radiant" else 3
            creeps = []
            for v in mm.values():
                if not isinstance(v, dict) or "xpos" not in v:
                    continue
                u = str(v.get("unitname", "")).lower()
                if ("creep" in u and "neutral" not in u or "siege" in u) and v.get("team") not in (my_team, None):
                    creeps.append(self._radiant_view(float(v["xpos"]), float(v["ypos"])))
            self.neutrals = [(str(v.get("unitname")), float(v["xpos"]), float(v["ypos"])) for v in mm.values()
                             if isinstance(v, dict) and "xpos" in v and str(v.get("unitname", "")).startswith("npc_dota_neutral_")]
            if creeps or any("creep" in str(v.get("unitname", "")) for v in mm.values() if isinstance(v, dict)):
                self.enemy_creeps, self.creeps_seen_at = creeps, self.clock
            elif self.creeps_seen_at is not None and self.clock is not None and self.clock - self.creeps_seen_at > 3:
                self.enemy_creeps = []
        h = p.get("hero") or {}
        self.hero_name = h.get("name", self.hero_name)
        self.alive = h.get("alive", self.alive)
        self.level = h.get("level", self.level)
        prev_mana = self.mana
        self.mana = float(h.get("mana", self.mana))
        self.max_mana = float(h.get("max_mana", self.max_mana)) or 1.0
        ab = p.get("abilities") or {}
        for a in ab.values():
            if not isinstance(a, dict):
                continue
            n = a.get("name", "")
            if n == "tinker_keen_teleport":
                lvl = int(a.get("level", 0))
                if lvl and not self.keen_level:
                    self.keen_learned_at = self.clock
                    self._say("keen", "keen")
                self.keen_level = lvl
                cd = float(a.get("cooldown", 0))
                if self.keen_cd - cd > 5 and cd <= 1:      # cooldown wiped: Rearm finished
                    self._on_rearm()
                self.keen_cd = cd
            elif n == "tinker_march_of_the_machines":
                self.march_level = int(a.get("level", self.march_level))
                cd = float(a.get("cooldown", 0))
                if cd > self.march_cd + 1 and self.trips:
                    self.trips[-1].marches += 1
                    self.trips[-1].seq.append("M")
                    self.last_march_at = self.clock
                self.march_cd = cd
            elif n == "tinker_laser":
                self.laser_level = int(a.get("level", self.laser_level))
                self.laser_ready = bool(a.get("can_cast", True)) and float(a.get("cooldown", 0)) == 0
                cd = float(a.get("cooldown", 0))
                if cd > self.laser_cd + 1 and self.trips:
                    self.trips[-1].seq.append("L")
                self.laser_cd = cd
        items = p.get("items") or {}
        if items:
            held = [v.get("name", "") for k, v in items.items()
                    if isinstance(v, dict) and k.startswith(NW_SLOTS) and v.get("name", "empty") != "empty"]
            self.items = held
            self.bottle_charges = next((int(v.get("charges", 0) or 0) for k, v in items.items()
                                        if isinstance(v, dict) and k.startswith("slot") and v.get("name") == "item_bottle"
                                        and k in ("slot0", "slot1", "slot2", "slot3", "slot4", "slot5")), 0)
            self.net_worth = self.gold + sum(ITEM_COSTS.get(n, 0) for n in held)
        self.has_blink = any(isinstance(v, dict) and v.get("name", "").startswith("item_blink")
                             or (isinstance(v, dict) and v.get("name") in ("item_overwhelming_blink", "item_swift_blink", "item_arcane_blink"))
                             for v in items.values())
        if "xpos" in h and "ypos" in h:
            x, y = float(h["xpos"]), float(h["ypos"])
            rv = self._radiant_view(x, y)
            if self.rv is not None and math.hypot(rv[0] - self.rv[0], rv[1] - self.rv[1]) > TELEPORT_JUMP and self.alive:
                self._on_landing(rv)
            elif self.rv is None or (not self.trips):
                if self.clock is not None and self.keen_level:
                    self._on_landing(rv)
            self.pos, self.rv = (x, y), rv
            self.loc = self._classify(*rv)
        # Rearm cast = mana drop while standing in fountain (checked after the landing,
        # because players often Rearm within the same update as the teleport lands)
        if self.trips and self.trips[-1].dest == "F" and self.loc == "F" and self.trips[-1].rearm_start is None                 and prev_mana - self.mana >= REARM_MANA_DROP:
            self.trips[-1].rearm_start = self.clock
        # last hits after position, so a kill is credited to where you are now
        if "last_hits" in pl:
            lh = int(pl["last_hits"])
            if self.lh_seen and lh != self.lh:
                self._on_lh(lh - self.lh)
                self.last_lh_change = self.clock
            elif not self.lh_seen:
                self.last_lh_change = self.clock
            self.lh, self.lh_seen = lh, True
        self._log_minute()
        self._rules()

    def _log_minute(self):
        c = self.clock
        if c is None or c < 0:
            return
        m = int(c // 60)
        if self.minute_log and self.minute_log[-1]["minute"] >= m:
            return
        imm_nw, top_nw = self.bench_nw(m)
        fstops = [t.length for t in self.trips if t.dest == "F" and t.length is not None]
        self.minute_log.append({
            "minute": m, "lh": self.lh, "net_worth": self.net_worth if self.net_worth is not None else "",
            "nw_vs_immortal": (self.net_worth - imm_nw) if self.net_worth is not None else "",
            "gold": self.gold, "gpm": self.gpm, "xpm": self.xpm, "level": self.level,
            "camp_trips": sum(1 for t in self.trips if t.dest in CAMP_STATIONS and t.camp_lh >= CAMP_MIN_LH),
            "fountain_stops": len(fstops), "stops_over_8s": sum(1 for f in fstops if f > 8),
            "items": " ".join(n.replace("item_", "") for n in self.items),
        })

    def bench_nw(self, minute=None):
        m = max(0, min(20, self.minute() if minute is None else minute))
        return DATA["bench_nw"]["immortal_median"][m], DATA["bench_nw"]["top10"][m]

    def _on_lh(self, gain):
        if gain <= 0 or not self.trips:
            return
        tr = self.trips[-1]
        tr.lh_gain += gain
        if self.loc in CAMP_STATIONS:
            tr.camp_lh += gain
            # a camp is 3-5 creeps; 1-2 last hits at a camp spot are usually lane creeps hit by Marches
            if tr.camp_lh >= CAMP_MIN_LH:
                self.last_farmed_minute[self.loc] = self.minute()
                if self.first_camp_kill is None and self.keen_level:
                    self.first_camp_kill = self.clock
                if self.loc == "C" and self.first_C_kill is None:
                    self.first_C_kill = self.clock

    def _on_rearm(self):
        if self.trips:
            self.trips[-1].seq.append("R")
        if self.trips and self.trips[-1].dest == "F" and self.trips[-1].rearm_at is None:
            self.trips[-1].rearm_at = self.clock
        elif self.loc != "F" and self.eff_mana < LOW_MANA:
            self.tips.append(Tip("Rearmed in the field under 300 mana: go home next time", "warn",
                                 until=(self.clock or 0) + 15))

    def _on_landing(self, rv):
        if self.clock is None:
            return
        if self.trips and self.trips[-1].end is None:
            self.trips[-1].end = self.clock
        dest = self._classify(*rv)
        self.trips.append(Trip(self.clock, dest, self.lh, self.mana))
        if dest == "C" and self.first_C_trip is None:
            self.first_C_trip = self.clock
            self.first_C_trip_mana = self.mana
            if self.mana < 450:
                self._say(f"lowC{self.clock}", "lowC")

    # ------------------------------------------------------------------ waves
    @staticmethod
    def _lane_of(x, y):
        if abs(x - y) < 1800:
            return "mid"
        if x < -4800 or y > 4800:
            return "top"
        if y < -4800 or x > 4800:
            return "bot"
        return None

    def _update_waves(self):
        """Group visible enemy lane creeps into waves on your half of the map."""
        groups = {}
        for x, y in self.enemy_creeps:
            if x + y > 1500:                      # their half: not a wave you should chase
                continue
            lane = self._lane_of(x, y)
            if lane == "mid":                     # side lanes are your teammates' job: only the mid wave counts
                groups.setdefault(lane, []).append((x, y))
        fx, fy = DATA["fountain"]["x"], DATA["fountain"]["y"]
        waves = []
        for lane, pts in groups.items():
            if len(pts) < 2:
                continue
            cx = sum(p[0] for p in pts) / len(pts); cy = sum(p[1] for p in pts) / len(pts)
            t1, t2 = T1[lane], T2[lane]
            # urgent only when the wave is clearly PAST your tier-1 or at your tier-2; a wave sitting at
            # your tier-1 is an ordinary wave (the top-10 treated it as filler, ~3 creeps)
            past_t1 = math.hypot(cx - fx, cy - fy) < math.hypot(t1[0] - fx, t1[1] - fy) - 500
            threat = past_t1 or math.hypot(cx - t2[0], cy - t2[1]) < 1500
            waves.append({"lane": lane, "rv": (cx, cy), "n": len(pts), "threat": threat,
                          "real": self._radiant_view(cx, cy)})     # radiant-view is its own inverse
        waves.sort(key=lambda w: (not w["threat"], math.hypot(w["rv"][0] - fx, w["rv"][1] - fy)))
        self.waves = waves

    def _wave_rec(self, w, why):
        self.wave_target = w["real"]
        letter = "B" if w["lane"] == "mid" else "W"
        return letter, f"{w['lane'].capitalize()} wave ({w['n']} creeps) {why}"

    # ------------------------------------------------------------------ advice
    def recommend(self) -> tuple[str, str]:
        """Next station to Keen to, with the reason (Jev's pick when the Jev advisor is on)."""
        rules = self._recommend_rules()
        tower = any(w["threat"] for w in self.waves) and self.eff_mana >= LOW_MANA
        if self.advisor is None or not self.keen_level or tower or rules[0] == "F" and self.loc != "F":
            return rules                        # before Keen / wave at your tower / out of mana: hard rules
        try:
            return self.advisor.pick(self, self._ready(), rules)
        except Exception:
            return rules

    def _ready(self) -> dict:
        c, mn = self.clock or 0, self.minute()
        soon = 60 - c % 60 <= 10
        return {k: self.last_farmed_minute[k] < mn or (soon and self.last_farmed_minute[k] == mn) for k in CAMP_STATIONS}

    def _recommend_rules(self) -> tuple[str, str]:
        c, lvl = self.clock or 0, self.level
        mana_ok_c = self.eff_mana >= TARGET["C_min_mana"] or (self.loc == "F")
        mn = self.minute()
        # camps respawn on the minute; count a camp as ready if it respawns before a Keen would land (~10 s)
        soon = 60 - c % 60 <= 10
        ready = {k: self.last_farmed_minute[k] < mn or (soon and self.last_farmed_minute[k] == mn) for k in CAMP_STATIONS}
        field_trips = [t for t in self.trips if t.dest != "F"]
        self.wave_target = None
        seen_waves = self.creeps_seen_at is not None
        if not self.keen_level:
            return "B", "Shove the wave so you can leave when Keen comes"
        if self.loc != "F" and self.eff_mana < LOW_MANA:
            return "F", f"{int(self.mana)} mana: go home, don't Rearm here"
        threat = next((w for w in self.waves if w["threat"]), None)
        if threat and self.eff_mana >= LOW_MANA:
            return self._wave_rec(threat, "at your tower: clear it, 2 Marches")
        if not any(t.dest in CAMP_STATIONS for t in field_trips):
            return "A", "First trip after Keen: the mid pair"
        march_ok = self.march_level == 0 or self.march_level >= C_MIN_MARCH   # 0 = unknown (old data)
        if c >= 360 and (lvl >= TARGET["C_min_level"] or (lvl >= 6 and self.mana >= 0.9 * self.max_mana)) \
                and ready["C"] and mana_ok_c and march_ok:
            return "C", "Hard + ancient: straight from fountain, 3 Marches"
        last2 = [t.dest for t in field_trips[-2:]]
        if len(last2) == 2 and all(d not in CAMP_STATIONS for d in last2):
            return ("A" if ready["A"] else "C" if ready["C"] else "D"), "Two trips without a camp: camp now"
        if ready["A"]:
            why = "Mid pair has respawned"
            if 0 < self.march_level < C_MIN_MARCH and c >= 360:
                why += f" (ancients after March {C_MIN_MARCH}, you have {self.march_level})"
            return "A", why
        if c >= 450 and ready["D"]:
            return "D", "Top-lane side camps"
        if (c >= 510 or self.has_blink) and ready["E"]:
            return "E", "Far camps"
        wait = 60 - int(c % 60)
        last_wave = bool(field_trips) and field_trips[-1].dest in ("B", "W", "lane")
        if wait > 15 and not last_wave and self.loc not in ("B", "lane"):
            if self.waves:
                return self._wave_rec(self.waves[0], f"camps respawn in {wait} s: one wave, then camp")
            if not seen_waves:
                return "B", f"Camps respawn in {wait} s: one wave, then camp"
        return "A", f"Camps respawn in {wait} s: refill, then Keen to A at :00"

    def _rules(self):
        self.tips = [t for t in self.tips if t.key == "" and t.until > (self.clock or 0)][-2:]  # one-off notes live 15 s
        c = self.clock
        if c is None:
            return
        self._update_waves()
        if self.keen_level and c >= 300:
            for w in self.waves:
                if w["threat"]:
                    self.tips.append(Tip(f"{w['lane'].capitalize()} wave pushing your tower ({w['n']} creeps)", "warn", key="wave"))
                    self._say(f"wave{w['lane']}{self.minute()}", "wave")
                    break
        if self.hero_name and self.hero_name != "npc_dota_hero_tinker":
            self.tips.append(Tip(f"Not Tinker ({self.hero_name.replace('npc_dota_hero_', '')}): coach idle", "info", key="hero"))
            return
        if not self.alive:
            self.tips.append(Tip("Dead: plan the first trip (fountain → camp)", "info", key="dead"))
            return
        tr = self.trips[-1] if self.trips else None
        # pre-Keen
        if not self.keen_level:
            if c >= 240:
                self.tips.append(Tip("Keen soon: shove the wave into their tower", "warn", key="prekeen"))
                self._say("prekeen", "prekeen")
            return
        # transition clock
        since = c - (self.keen_learned_at or c)
        if self.first_camp_kill is None:
            lvl = "good" if since < 30 else ("warn" if since < TARGET["first_camp_after_keen_s"] else "bad")
            self.tips.append(Tip(f"First camp: {int(since)} s since Keen (target ≤ 40 s)", lvl, key="switch"))
            if since > 40:
                self._say("switch40", "switch40")
        # fountain stopwatch
        if tr and tr.dest == "F" and tr.end is None and self.loc == "F":
            dwell = c - tr.start
            if tr.rearm_start is None and tr.rearm_at is None and dwell >= 2:
                self.tips.append(Tip("REARM", "bad" if dwell >= 3.5 else "warn", key="rearm"))
                if dwell >= 3.5:
                    self._say(f"rearm{tr.start}", "rearm")
            if dwell >= TARGET["fountain_stop_s"]:
                self.tips.append(Tip(f"GO: {dwell:.0f} s in fountain", "bad", key="go"))
                if not tr.spoke_idle and dwell >= 9:
                    tr.spoke_idle = True
                    self.speech_queue.append(("go", VOICE_LINES["go"]))
        # field
        elif tr:
            if self.eff_mana < LOW_MANA:
                self.tips.append(Tip(f"{int(self.mana)} mana: Keen home", "warn", key="lowmana"))
                if c - tr.start > 3:
                    self._say(f"lowmana{tr.start}", "lowmana")
            if tr.dest == "C" and tr.mana_start < 450 and c - tr.start < 20:
                self.tips.append(Tip(f"Only {int(tr.mana_start)} mana for ancients: go F → C next time", "bad", key="cmana"))
            mcost = MARCH_COST[max(0, min(4, self.march_level))]
            if self.march_level and self.mana < KEEP_MANA + mcost and tr.marches:
                self.tips.append(Tip(f"Keep {KEEP_MANA} mana for home: no more Marches, Laser or Keen", "warn", key="reserve"))
            if tr.dest == "lane" and c - tr.start < 12:
                self.tips.append(Tip("Side lanes are your teammates': mid wave or camps", "info", key="sidelane"))
            if tr.dest == "B" and tr.marches >= 3:
                self.tips.append(Tip("3+ Marches on a wave: that's a camp's worth", "warn", key="wave"))
            if self.loc == "enemy" and c < 900:
                self.tips.append(Tip("Enemy side before 15:00: risky, low payoff", "warn", key="enemy"))
            if tr.camp_lh and self.loc in CAMP_STATIONS and 47 <= c % 60 <= 54:
                self.tips.append(Tip("xx:53: pull the next camp to stack it", "info", key="stack"))
        # no farm
        if c >= 300 and self.last_lh_change is not None and c - self.last_lh_change >= 40 and self.loc != "F":
            self.tips.append(Tip(f"{int(c - self.last_lh_change)} s without a creep", "bad", key="nofarm"))
            self._say(f"nofarm{int(self.last_lh_change)}", "nofarm")
        # checkpoints
        if c >= TARGET["first_C_trip"] and self.first_C_trip is None and self.level >= 6:
            self.tips.append(Tip("7:30 and no ancient trip yet: C from fountain", "bad", key="ctime"))
            self._say("ctime", "ctime")
        rec, why = self.recommend()
        if self.loc == "F" and rec == "C":
            self._say(f"goC{self.minute()}", "goC")

    # ------------------------------------------------------------------ camp finisher
    def camp_status(self) -> Optional[dict]:
        """At a camp after a March: how many neutrals are left and the fastest way to finish them."""
        if self.loc not in CAMP_STATIONS or self.pos is None or not self.trips or self.last_march_at is None:
            return None
        tr = self.trips[-1]
        if tr.dest not in CAMP_STATIONS or "M" not in tr.seq or self.clock is None:
            return None
        since = self.clock - self.last_march_at
        if since < MARCH_WORK_S:
            return {"state": "working", "left": None, "text": f"March working… {MARCH_WORK_S - since:.0f}s", "action": None}
        x, y = self.pos
        left = [n for n, nx, ny in self.neutrals if math.hypot(nx - x, ny - y) < 1000]
        if not left:
            return {"state": "clear", "left": 0, "text": "Camp clear", "action": "keen"}
        # what one Laser / one March can still do to what's standing
        hp = [NEUTRAL_STATS.get(n, {}).get("hp", 600) for n in left]
        laser = LASER_DMG[max(0, min(4, self.laser_level))]
        if len(left) == 1 and self.laser_level and self.laser_ready:
            return {"state": "left", "left": 1, "text": "1 left → Laser", "action": "laser"}
        if self.eff_mana < LOW_MANA:
            return {"state": "left", "left": len(left), "text": f"{len(left)} left, low mana → Keen home", "action": "keen"}
        big = max(hp) > laser * 2
        cost = REARM_COST[max(1, min(3, (self.level >= 18) + (self.level >= 12) + 1))] + MARCH_COST[max(1, min(4, self.march_level or 1))]
        if self.mana - cost < KEEP_MANA:
            return {"state": "left", "left": len(left), "text": f"{len(left)} left: keep {KEEP_MANA} mana → Keen home", "action": "keen"}
        return {"state": "left", "left": len(left), "text": f"{len(left)} left → Rearm + March" + (" (big one)" if big and len(left) == 1 else ""),
                "action": "rearm"}

    # ------------------------------------------------------------------ guide
    PLANS = {
        # Immortal full clears of a camp pair used ~3 Marches (+ Laser about every other trip); ancients 3.2 + 1 Laser
        "A": ["March from behind", "Rearm", "March again", "Rearm", "Third March", "Laser the last one", "Keen home"],
        "D": ["March from behind", "Rearm", "March again", "Rearm", "Third March", "Laser the last one", "Keen home"],
        "E": ["March from behind", "Rearm", "March again", "Rearm", "Third March", "Laser the last one", "Keen home"],
        "C": ["March through both camps", "Rearm", "March", "Rearm", "March", "Laser the last creep", "Keen home"],
        "B": ["March the wave", "Rearm", "One more March (2 max)", "Keen home"],
        "W": ["March the wave", "Rearm", "One more March (2 max)", "Keen home"],
        "lane": ["March the wave", "Rearm", "One more March (2 max)", "Keen home"],
    }
    TOKENS = {"A": "MRMRML", "D": "MRMRML", "E": "MRMRML", "C": "MRMRML", "B": "MRM", "W": "MRM", "lane": "MRM"}
    LOW_MARCH_PLAN = ["March from behind", "Rearm", "March again", "Rearm", "Third March", "Rearm",
                      "Fourth March (low March lvl)", "Laser the last one", "Keen home"]

    def guide(self) -> dict:
        """What to press right now, as an ordered step list with the current step marked."""
        rec, why = self.recommend()
        nxt = f"Keen → {rec} · {STATION_NAMES.get(rec, rec)}"
        tr = self.trips[-1] if self.trips else None
        c = self.clock or 0
        if self.hero_name and self.hero_name != "npc_dota_hero_tinker":
            return {"title": "Not playing Tinker", "steps": [], "cur": -1}
        if not self.alive:
            return {"title": "DEAD · plan the first trip", "steps": ["Respawn", "Rearm", f"Keen → {rec}"], "cur": 0}
        if self.drill_note:
            return {"title": "DRILL", "steps": [self.drill_note, "Skill: Keen 1, March 3, Laser 1, Rearm 1", "Keen → Fountain → A"], "cur": 0}
        if not self.keen_level:
            steps = ["Shove the wave", "Learn Keen Teleport", "Keen → Fountain", "Rearm → Keen → A"]
            return {"title": "LANE · before Keen", "steps": steps, "cur": 0}
        if self.loc == "F" and tr and tr.dest == "F":
            dwell = c - tr.start
            rearmed = tr.rearm_start is not None or tr.rearm_at is not None
            steps = ["Rearm", f"Keen → {rec}"]
            return {"title": f"FOUNTAIN · {dwell:.0f} s (target ≤ 7)", "steps": steps, "cur": 1 if rearmed else 0}
        if tr and tr.dest in self.PLANS:
            plan, want = self.PLANS[tr.dest], self.TOKENS[tr.dest]
            if tr.dest in ("A", "D", "E") and 0 < self.march_level < 3:
                plan, want = self.LOW_MARCH_PLAN, "MRMRMRML"
            done = 0
            for tok in tr.seq:                 # greedy match of what you pressed against the plan
                if done < len(want) and tok == want[done]:
                    done += 1
            mcost = MARCH_COST[max(0, min(4, self.march_level))]
            # real mana, not Bottle charges: the benchmark (Immortals come home with ~226) is real mana
            if done < len(want) and want[done] == "M" and self.march_level and self.mana - mcost < KEEP_MANA:
                plan = plan[:done] + [f"Keen home (keep {KEEP_MANA} mana)"]
            elif self.eff_mana < LOW_MANA or done >= len(want):
                done = len(plan) - 1           # out of mana (Bottle too) or plan finished: go home
            title = f"{tr.dest} · {STATION_NAMES[tr.dest]}  ({c - tr.start:.0f} s, +{tr.lh_gain} LH)"
            return {"title": title, "steps": plan, "cur": done}
        if self.loc == "enemy":
            return {"title": "ENEMY SIDE", "steps": ["Get out: Keen home", nxt], "cur": 0}
        return {"title": STATION_NAMES.get(self.loc, self.loc).upper(), "steps": ["Keen home", nxt], "cur": 0}

    # ------------------------------------------------------------------ outputs
    def checklist(self):
        k = self.keen_learned_at
        c = self.clock or 0
        fstops = [t.length for t in self.trips if t.dest == "F" and t.length is not None and 300 <= t.start < 600]
        camp_trips = sum(1 for t in self.trips if t.dest in CAMP_STATIONS and t.camp_lh >= CAMP_MIN_LH and 300 <= t.start < 600)
        def mark(ok, done):
            return "✓" if ok else ("✗" if done else "…")
        rows = [
            ("Keen learned", fmt(k), mark(k is not None, c > 420)),
            ("First camp kill ≤ Keen+40 s", fmt(self.first_camp_kill),
             mark(self.first_camp_kill is not None and k is not None and self.first_camp_kill - k <= 40,
                  k is not None and c - k > 40)),
            ("C trip ≤ 7:30 (≥600 mana)", f"{fmt(self.first_C_trip)} {int(self.first_C_trip_mana) if self.first_C_trip_mana else ''}",
             mark(self.first_C_trip is not None and self.first_C_trip <= 450 and (self.first_C_trip_mana or 0) >= 450, c > 450)),
            ("First ancient ≤ 7:45", fmt(self.first_C_kill), mark(self.first_C_kill is not None and self.first_C_kill <= 465, c > 465)),
            ("Camp trips 5–10 ≥ 7", str(camp_trips), mark(camp_trips >= 7, c >= 600)),
            ("Fountain stops > 8 s (5–10)", str(sum(1 for f in fstops if f > 8)),
             "✗" if any(f > 8 for f in fstops) else ("✓" if c >= 600 and fstops else "…")),
        ]
        return rows

    def bench(self):
        m = max(0, min(20, self.minute()))
        frac = ((self.clock or 0) % 60) / 60 if 0 <= (self.clock or 0) < 1200 else 0
        def at(arr):
            return arr[m] + (arr[min(20, m + 1)] - arr[m]) * frac
        return at(DATA["bench_lh"]["immortal_median"]), at(DATA["bench_lh"]["top10"])

    def view(self):
        tr = self.trips[-1] if self.trips else None
        rec, why = self.recommend()
        stop = None
        if tr and tr.dest == "F" and tr.end is None and self.clock is not None:
            stop = self.clock - tr.start
        return {
            "clock": self.clock, "state": self.game_state, "level": self.level, "mana": self.mana, "max_mana": self.max_mana,
            "lh": self.lh, "bench": self.bench(), "loc": self.loc, "rec": rec, "why": why, "tips": self.tips,
            "stop": stop, "trip": tr, "trips": self.trips[-14:], "checklist": self.checklist(), "pos": self.pos,
            "team": self.team, "alive": self.alive, "hero": self.hero_name, "guide": self.guide(),
            "net_worth": self.net_worth, "gpm": self.gpm, "bottle": self.bottle_charges, "eff_mana": self.eff_mana,
            "camp": self.camp_status(),
            "wave_target": self.wave_target, "waves": self.waves, "march_level": self.march_level,
        }

    def summary_row(self):
        at10 = next((r for r in self.minute_log if r["minute"] == 10), {})
        fstops = [t.length for t in self.trips if t.dest == "F" and t.length is not None and 300 <= t.start < 600]
        return {
            "match": self.game_id, "date": time.strftime("%Y-%m-%d %H:%M"), "team": self.team,
            "first_keen": fmt(self.keen_learned_at), "first_camp_kill": fmt(self.first_camp_kill),
            "first_C_trip": fmt(self.first_C_trip), "C_trip_mana": int(self.first_C_trip_mana or 0),
            "first_ancient": fmt(self.first_C_kill),
            "camp_trips_5_10": sum(1 for t in self.trips if t.dest in CAMP_STATIONS and t.camp_lh >= CAMP_MIN_LH and 300 <= t.start < 600),
            "fountain_stops_over_8s": sum(1 for f in fstops if f > 8),
            "median_fountain_stop": round(statistics.median(fstops), 1) if fstops else "",
            "lh_at_10": at10.get("lh", self.lh),
            "nw_at_10": at10.get("net_worth", ""),
            "nw_vs_immortal_10": at10.get("nw_vs_immortal", ""),
            # new columns go LAST: append_row maps older rows' extra values onto new fields in order
            "home_mana": int(statistics.median([t.mana_start for t in self.trips if t.dest == "F" and 300 <= t.start < 600]))
                         if any(t.dest == "F" and 300 <= t.start < 600 for t in self.trips) else "",
        }
