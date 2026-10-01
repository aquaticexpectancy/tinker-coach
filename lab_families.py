"""Clean creep families per camp, from a lab run's logged spawns -> lab_families.json (the lab spawns these).

    python lab_families.py [run.jsonl]       default: the latest run with lab results

The spawner-based lab logged every camp's creeps, but blocked or half-cleared camps merged sets ("kobolds +
forest trolls") or stacked one twice. Every logged set is split into its groups, and per camp and group the most
common version is kept.
"""
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GROUPS = [("kobold", "kobold"), ("forest_troll", "forest_troll"), ("gnoll", "gnoll"), ("ghost", "fel_beast|ghost"),
          ("wildkin", "wildkin"), ("centaur", "centaur"), ("satyr", "satyr"), ("furbolg", "polar_furbolg"),
          ("warpine", "warpine"), ("dark_troll", "dark_troll"), ("wolf", "wolf"), ("ogre", "ogre"),
          ("mud_golem", "mud_golem"), ("dragon", "black_dra"), ("frost", "frostbitten|ice_shaman"),
          ("lizard", "thunder_lizard"), ("granite", "granite_golem|rock_golem"), ("prowler", "prowler"),
          ("frog", "frog")]


# the standard set where it's known: the logs only decide which families a camp gets (stacked or half-cleared
# camps logged e.g. 5 ogres, 2 kobold taskmasters, forest trolls without their high priest)
CANON = {"kobold": ["kobold", "kobold", "kobold", "kobold_taskmaster", "kobold_tunneler"],
         "forest_troll": ["forest_troll_berserker", "forest_troll_berserker", "forest_troll_high_priest"],
         "gnoll": ["gnoll_assassin", "gnoll_assassin", "gnoll_assassin"],
         "ghost": ["fel_beast", "fel_beast", "ghost"],
         "wildkin": ["enraged_wildkin", "wildkin", "wildkin"],
         "centaur": ["centaur_khan", "centaur_outrunner", "centaur_outrunner"],
         "furbolg": ["polar_furbolg_champion", "polar_furbolg_ursa_warrior"],
         "warpine": ["warpine_raider", "warpine_raider"],
         "dark_troll": ["dark_troll", "dark_troll", "dark_troll_warlord"],
         "wolf": ["alpha_wolf", "giant_wolf", "giant_wolf"],
         "ogre": ["ogre_magi", "ogre_mauler", "ogre_mauler"],
         "mud_golem": ["mud_golem", "mud_golem"],
         "dragon": ["black_dragon", "black_drake", "black_drake"],
         "frost": ["frostbitten_golem", "frostbitten_golem", "ice_shaman"],
         "lizard": ["big_thunder_lizard", "small_thunder_lizard", "small_thunder_lizard"],
         "granite": ["granite_golem", "rock_golem", "rock_golem"],
         "prowler": ["prowler_acolyte", "prowler_acolyte", "prowler_shaman"]}


# camp types: which families belong to which kind of camp (ancients only ever at an ancient camp)
TYPE = {"kobold": "small", "forest_troll": "small", "gnoll": "small", "ghost": "small",
        "wildkin": "medium", "furbolg": "medium", "warpine": "medium", "dark_troll": "medium", "satyr": "medium",
        "centaur": "hard", "ogre": "hard", "mud_golem": "hard", "wolf": "hard",
        "dragon": "ancient", "frost": "ancient", "lizard": "ancient", "granite": "ancient", "prowler": "ancient",
        "frog": "frog"}


def fam_type(f):
    g = group(f[0])
    if g == "satyr":
        return "hard" if len(f) >= 4 else "medium"                          # 4 satyrs: the hard-camp version
    return TYPE.get(g, "?")


def camp_type(fams):
    return "/".join(sorted({fam_type(f) for f in fams}))


def group(name):
    for g, pats in GROUPS:
        if any(p in name for p in pats.split("|")):
            return g
    return name


def main(path=None):
    if not path:
        runs = [p for p in glob.glob(os.path.join(HERE, "bot_runs", "*.jsonl")) if '"lab_result"' in open(p, encoding="utf-8").read()]
        path = max(runs, key=os.path.getmtime)
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    spots = [r for r in rows if r.get("kind") == "camp_spot" and not r.get("dropped")]
    # split every logged set into its groups (merged camps hold two families), count each group's version
    seen = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
    for r in rows:
        if r.get("kind") == "lab_result":
            for c in r["camps"]:
                by = collections.defaultdict(list)
                for x in c["creeps"]:
                    by[group(x["name"])].append(x["name"])
                for g, names in by.items():
                    seen[c["camp"]][g][tuple(sorted(names))] += 1
    out = []
    for i, s in enumerate(spots, 1):
        fams = []
        for g, versions in sorted(seen.get(i, {}).items()):
            # the most common version (a stacked camp doubles a set; a half-cleared one is missing creeps),
            # ties to the larger, and a lone creep only when nothing else was seen
            best = max(versions.items(), key=lambda kv: (len(kv[0]) > 1, kv[1], len(kv[0])))[0]
            fams.append(tuple(CANON.get(g, best)))
        kind = camp_type(fams) if fams else "?"
        out.append({"station": s["station"], "x": s["to_x"], "y": s["to_y"], "type": kind,
                    "families": [list(f) for f in fams]})
        print(f"{s['station']} {kind} camp at ({s['to_x']}, {s['to_y']}): " + " | ".join("+".join(f) for f in fams))
    json.dump(out, open(os.path.join(HERE, "lab_families.json"), "w"), indent=1)
    print("-> lab_families.json")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
