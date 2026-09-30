"""Score Jev's station choice against what Immortal Tinkers actually did (from their replays).

    python jev_eval.py [variant] [dev|test|all]
"""
import collections, concurrent.futures as cf, json, sys, random
import jev_advisor
from typesafe_sdk import Choice, TypeSafeClient

DATA = r"C:/Users/docky/AppData/Local/Temp/claude/C--Users-docky-Documents-tinker/b475f138-0667-4ae0-8fbe-5b506d536a40/scratchpad/data/jev_station_set.json"
SET = json.load(open(DATA))
games = sorted({d["game"] for d in SET}); random.Random(7).shuffle(games)
DEV = set(games[: len(games) // 2])
client = TypeSafeClient(api_key=jev_advisor.api_key(), model="jev-latest", timeout=15)

BASE_Q = ("Tinker is farming the jungle in Dota 2, Keen Teleporting to a spot, clearing it with March of the Machines and "
          "Rearm, and going back to fountain for mana. Using `tinker`, `camps`, `mid_wave`, `last_trips` and `guidance`, "
          "where should Tinker Keen to next to earn the most gold over the next minute?")

IMM_Q = ("An Immortal-rank Tinker is in fountain between 5 and 10 minutes, about to Keen out. Given `tinker`, `camps`, "
         "`mid_wave` and `last_trips`, and the habits in `immortal_habits`, where would an Immortal Tinker Keen to next?")
IMM_HABITS = [
    "They alternate: after a camp trip (A, C, D) they usually take the mid wave next; after a wave they go to a camp.",
    "Right after the mid pair A, about 7 in 10 go to the mid wave.",
    "After a mid wave they go to the ancients C or the mid pair A about equally, and to the wave again about 1 in 4.",
    "The mid wave is the most common destination overall (about 45% of trips): it keeps mid from pushing and fills time.",
    "When the camps respawn within ~15 s, or the mid pair A has already been cleared this minute, most take the mid wave.",
    "The ancients C need March level 4; once that's there, C becomes a regular stop, often straight after a wave.",
    "D (top-side camps) and E (far camps) are occasional extras (about 1 in 10 and 1 in 30 trips).",
    "Low mana makes the short mid-wave trip (2 Marches) more likely than a camp (3 Marches).",
]
IMM_TEXT = dict(jev_advisor.OPTION_TEXT,
    B="Mid lane wave: 2 Marches on the enemy wave near your tier-1 tower; Immortals' most common destination",
    A="Mid pair (A): the two camps next to mid, 3 Marches",
    C="Ancients (C): hard camp + ancients, 3 Marches and a Laser; needs March level 4",
    F="Wait in fountain (Immortals almost never do this)")
VARIANTS = {"base": {"q": BASE_Q, "guidance": jev_advisor.GUIDANCE, "text": jev_advisor.OPTION_TEXT},
            "immortal": {"q": IMM_Q, "guidance": IMM_HABITS, "text": IMM_TEXT, "key": "immortal_habits"}}


def options(d):
    o = [k for k in "ACDE" if d["state"]["camps"][k]["ready"]] + ["B", "F"]
    if d["label"] not in o:
        o.append(d["label"])
    return o


def ask(d, v):
    st = dict(d["state"], **{v.get("key", "guidance"): v["guidance"]})
    opts = options(d)
    r = client.system_one(state=st, questions={"pick": Choice(instructions=v["q"], criteria={o: v["text"][o] for o in opts})})
    ch = r.choices["pick"]
    return ch.choice, dict(ch.probabilities)


def run(name, split="dev"):
    v = VARIANTS[name]
    ds = [d for d in SET if (split == "all") or ((d["game"] in DEV) == (split == "dev"))]
    with cf.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda d: ask(d, v), ds))
    hit = sum(p == d["label"] for (p, _), d in zip(res, ds))
    ll = sum(-__import__("math").log(max(1e-6, pr.get(d["label"], 0))) for (_, pr), d in zip(res, ds)) / len(ds)
    conf = collections.Counter((d["label"], p) for (p, _), d in zip(res, ds))
    picks = collections.Counter(p for p, _ in res)
    print(f"[{name} / {split}] n={len(ds)} accuracy {hit/len(ds):.0%}  log-loss {ll:.2f}  picks {dict(picks)}")
    labels = collections.Counter(d["label"] for d in ds)
    for lab in sorted(labels):
        row = {p: conf[(lab, p)] for p in sorted(picks) if conf[(lab, p)]}
        print(f"   Immortal {lab} ({labels[lab]}): Jev -> {row}")
    return hit / len(ds)


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "base", sys.argv[2] if len(sys.argv) > 2 else "dev")


# ---------------------------------------------------------------- split variant: wave yes/no + which camp
from typesafe_sdk import Noul

WAVE_HABITS = [
    "Immortal Tinkers alternate camp trips and mid-wave trips.",
    "After a camp trip (A, C or D) the next trip is usually the mid wave (about 7 in 10 after the mid pair A).",
    "After a mid-wave trip the next trip is usually a camp (about 3 in 4).",
    "When the camps respawn within ~15 s, or the mid pair A was already cleared this minute, they usually take the wave.",
    "With little mana they prefer the short wave trip.",
]
CAMP_HABITS = [
    "The mid pair A is the default camp; the ancients C are the other main camp once March is level 4.",
    "After a mid-wave trip, C and A are about equally likely; after A (if A isn't up) they go to C.",
    "D (top-side) is an occasional extra, mostly from 7:00 on when A and C were just cleared; E (far) is rare.",
    "They don't go back to a camp they cleared this minute.",
]


def ask_split(d):
    st = dict(d["state"])
    camps = [k for k in "ACDE" if d["state"]["camps"][k]["ready"]] or ["A"]
    q = {"wave": Noul(instructions={"habits": WAVE_HABITS, "question": "Given `tinker`, `camps`, `mid_wave` and "
                                    "`last_trips`, would an Immortal Tinker take the mid wave on this trip instead of a camp?"}),
         "camp": Choice(instructions={"habits": CAMP_HABITS, "question": "If this Immortal Tinker goes to a camp now, "
                                      "given `tinker`, `camps` and `last_trips`, which one?"},
                        criteria={k: IMM_TEXT[k] for k in camps})}
    r = client.system_one(state=st, questions=q)
    return r.nouls["wave"].noul, r.choices["camp"].choice, dict(r.choices["camp"].probabilities)


def run_split(split="dev", thresholds=(0.3, 0.4, 0.5, 0.6, 0.7)):
    ds = [d for d in SET if (split == "all") or ((d["game"] in DEV) == (split == "dev"))]
    with cf.ThreadPoolExecutor(8) as ex:
        res = list(ex.map(ask_split, ds))
    best = None
    for th in thresholds:
        picks = ["B" if w >= th else c for (w, c, _) in res]
        acc = sum(p == d["label"] for p, d in zip(picks, ds)) / len(ds)
        print(f"[split / {split}] wave threshold {th:.2f}: accuracy {acc:.0%}  picks {dict(collections.Counter(picks))}")
        if not best or acc > best[1]:
            best = (th, acc, picks)
    th, acc, picks = best
    conf = collections.Counter((d["label"], p) for p, d in zip(picks, ds))
    for lab in "ABCDE":
        n = sum(1 for d in ds if d["label"] == lab)
        if n: print(f"   Immortal {lab} ({n}): Jev -> " + str({p: conf[(lab, p)] for p in "ABCDE" if conf[(lab, p)]}))
    camp_ds = [(c, d) for (w, c, _), d in zip(res, ds) if d["label"] != "B"]
    print(f"   camp choice alone, when the Immortal went to a camp: {sum(c == d['label'] for c, d in camp_ds)/len(camp_ds):.0%} of {len(camp_ds)}")
    return res, ds


ALT_Q = ("You are choosing the next Keen for an Immortal-rank Tinker (5-10 minutes). Follow `playbook` step by step "
         "using `last_trips`, `camps`, `tinker` and `seconds_until_camps_respawn`. Where does it Keen to?")
PLAYBOOK = [
    "1. If the last trip was a camp (A, C, D or E), or there was no trip yet: go to the mid wave (B).",
    "2. If the last trip was the mid wave: go to a camp. Prefer the ancients C when `camps.C.ready` and March level "
    "is 4; otherwise the mid pair A when `camps.A.ready`; otherwise D.",
    "3. Exception: if the mid pair A has not been farmed yet this minute and the last trip was not A, A is also fine.",
    "4. Never wait in fountain.",
]
VARIANTS["playbook"] = {"q": ALT_Q, "guidance": PLAYBOOK, "text": IMM_TEXT, "key": "playbook"}
