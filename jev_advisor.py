"""Jev (TypeSafe System One) picks the next station: which camp, the mid wave, or fountain.

Code keeps the facts and the hard rules (what has respawned, mana, March level, where the mid
wave is); Jev only chooses among the options that are legal right now, plus one yes/no on
stacking. Requests run in a background thread so the HUD never waits on the network; until an
answer for the current decision arrives, the rule-based pick is shown.

    API key: TYPESAFE_API_KEY in the environment, or tinker_coach/typesafe_key.txt
    Every decision (Jev's pick, its probabilities and the rule-based pick) goes to jev_log.jsonl.
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
import time

HERE = pathlib.Path(__file__).parent
KEY_FILE = HERE / "typesafe_key.txt"
LOG = HERE / "jev_log.jsonl"
MIN_CONFIDENCE = 0.35        # below this the rule-based pick is shown instead (Jev's still logged)

OPTION_TEXT = {
    "A": "Camps next to mid (A pair): closest camps, quick 3-March clear",
    "C": "Hard camp + ancients (C): the most gold per trip, needs high mana and March level 4",
    "D": "Top-side jungle camps (D): extra camps once A is on cooldown",
    "E": "Far bottom camps (E): the furthest camps, worth it later or with Blink",
    "B": "Mid lane wave: March the enemy mid wave on your half of the map",
    "F": "Fountain: go home / stay to refill mana and wait for camps to respawn",
}
GUIDANCE = [
    "From 44 Immortal Tinker games (patch 7.41): a camp trip pays about 6 kills, a mid-wave trip about 3.",
    "Immortals open the jungle fountain -> wave or mid pair (A); A and C (hard + ancients) are the main camps, "
    "D (top-side) joins from ~7:30, E (far bottom) later.",
    "The mid wave is worth it when it is pushing past your tier-1 tower, or when every ready camp is more than ~15 s "
    "from respawning; never two waves in a row.",
    "Camps get a new set of creeps every full minute (:00), even when leftovers are still there (patch 7.41), so "
    "leftovers stack up; Immortals leave about a third of a camp alive and move on.",
    "Fountain stops are ~7.5 s (Bottle, Rearm, Bottle, Keen); come home with about 200 mana, not empty.",
    "Ancients (C) need March level 4 and ~600+ mana to clear in one visit.",
]


def api_key() -> str | None:
    k = os.environ.get("TYPESAFE_API_KEY")
    if k:
        return k.strip()
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip() or None
    return None


def _fmt(t):
    t = int(t or 0)
    return f"{t // 60}:{t % 60:02d}"


class JevAdvisor:
    def __init__(self, mode: str = "jev", log=print):
        from typesafe_sdk import TypeSafeClient     # imported here so the coach runs without the SDK
        self.client = TypeSafeClient(api_key=api_key(), model="jev-latest", timeout=8.0)
        self.mode = mode              # "jev": show Jev's pick · "shadow": show rules, log Jev
        self.log = log
        self.pending = None           # decision key being asked
        self.answer = None            # (key, pick, prob, confidence, stack_p)
        self.errors = 0
        self.lock = threading.Lock()

    # ------------------------------------------------------------------ facts -> options
    @staticmethod
    def options(eng, ready, rules_pick) -> list[str]:
        """Stations that are legal right now (the hard rules stay in code)."""
        from engine import C_MIN_MARCH, LOW_MANA, TARGET
        opts = [k for k in ("A", "D", "E") if ready.get(k)]
        march_ok = eng.march_level == 0 or eng.march_level >= C_MIN_MARCH
        if ready.get("C") and march_ok and (eng.clock or 0) >= 360 and \
                (eng.eff_mana >= TARGET["C_min_mana"] or eng.loc == "F"):
            opts.append("C")
        if eng.waves or eng.creeps_seen_at is None:
            opts.append("B")
        opts.append("F")
        if rules_pick in OPTION_TEXT and rules_pick not in opts:
            opts.append(rules_pick)
        return opts

    @staticmethod
    def state(eng, ready, rules_pick, rules_why) -> dict:
        c = eng.clock or 0
        field = [t for t in eng.trips if t.dest != "F"]
        wave = eng.waves[0] if eng.waves else None
        return {
            "game_clock": _fmt(c),
            "seconds_until_camps_respawn": 60 - int(c % 60),
            "tinker": {
                "location": {"F": "fountain"}.get(eng.loc, eng.loc),
                "level": eng.level, "max_mana": int(eng.max_mana),
                "mana": int(eng.max_mana) if eng.loc == "F" else int(eng.mana),   # fountain refills before you leave
                "bottle_charges": eng.bottle_charges, "march_level": eng.march_level,
                "laser_level": eng.laser_level, "has_blink": eng.has_blink,
            },
            "camps": {k: {"ready": bool(ready.get(k)), "last_cleared_minute": eng.last_farmed_minute.get(k)}
                      for k in ("A", "C", "D", "E")},
            "mid_wave": ({"visible": True, "creeps": wave["n"], "pushing_into_your_tower": wave["threat"]}
                         if wave else {"visible": False}),
            "last_trips": [{"to": t.dest, "last_hits": t.lh_gain, "seconds": round((t.end or c) - t.start)}
                           for t in field[-4:]],
            "rule_based_suggestion": {"station": rules_pick, "why": rules_why},
            "guidance": GUIDANCE,
        }

    # ------------------------------------------------------------------ decision
    def pick(self, eng, ready, rules: tuple[str, str]) -> tuple[str, str]:
        """Called from Engine.recommend(): returns (station, why)."""
        rules_pick, rules_why = rules
        # decisions happen in fountain, or at a camp once it is clear (the next Keen is the decision)
        cs = eng.camp_status() if eng.loc != "F" else None
        if eng.loc != "F" and not (cs and cs["state"] == "clear"):
            return rules
        opts = self.options(eng, ready, rules_pick)
        if len(opts) <= 1:
            return rules
        key = (len(eng.trips), eng.loc, int((eng.clock or 0) // 60), tuple(opts))
        with self.lock:
            ans = self.answer
            busy = self.pending is not None
        if (ans is None or ans[0] != key) and not busy and self.errors < 5:
            self._ask(key, eng, ready, opts, rules_pick, rules_why)
        if ans is None or ans[0][:2] != key[:2] or self.mode != "jev":
            return rules
        _, pick, prob, conf, stack_p = ans
        if conf < MIN_CONFIDENCE:
            return rules_pick, f"{rules_why} (Jev unsure: {pick} {prob:.0%})"
        why = f"Jev {prob:.0%}: {OPTION_TEXT[pick].split(':')[0]}"
        if pick != rules_pick:
            why += f" · rules said {rules_pick}"
        if stack_p >= 0.6 and pick in ("A", "C", "D", "E"):
            why += " · stack at :53"
        return pick, why

    def _ask(self, key, eng, ready, opts, rules_pick, rules_why):
        from typesafe_sdk import Choice, Noul
        st = self.state(eng, ready, rules_pick, rules_why)
        questions = {
            "next_station": Choice(
                instructions="Tinker is farming the jungle in Dota 2 between 5 and 20 minutes, using Keen "
                             "Teleport to jump to a spot, clearing it with March of the Machines and Rearm, and "
                             "returning to fountain for mana. Using the facts in `tinker`, `camps`, `mid_wave` and "
                             "`last_trips` and the `guidance`, where should Tinker Keen to next to earn the most "
                             "gold over the next minute?",
                criteria={o: OPTION_TEXT[o] for o in opts},
            ),
            "stack": Noul(
                instructions="On this trip, is it worth pulling a camp at :53 so that it stacks (two sets of "
                             "creeps next minute), given Tinker's mana, March level and the time on `game_clock`?",
                criteria={"true": "Stacking pays: Tinker can clear a double camp next minute",
                          "false": "Just clear what is there and move on"},
            ),
        }
        with self.lock:
            self.pending = key

        def run():
            t0 = time.time()
            try:
                r = self.client.system_one(state=st, questions=questions)
                ch = r.choices["next_station"]
                probs = dict(ch.probabilities)
                stack_p = float(r.nouls["stack"].noul)
                with self.lock:
                    self.answer = (key, ch.choice, probs.get(ch.choice, 0.0), float(ch.confidence), stack_p)
                    self.errors = 0
                entry = {"t": time.time(), "clock": st["game_clock"], "state": st, "options": opts,
                         "jev": ch.choice, "probs": probs, "confidence": ch.confidence, "stack": stack_p,
                         "rules": rules_pick, "latency_s": round(time.time() - t0, 2), "mode": self.mode}
                with open(LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception as ex:                 # network/API trouble: fall back to rules, keep playing
                with self.lock:
                    self.errors += 1
                self.log(f"Jev request failed ({type(ex).__name__}): {ex}")
            finally:
                with self.lock:
                    self.pending = None

        threading.Thread(target=run, daemon=True).start()
