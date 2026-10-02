# Tinker Coach

Live coach for the Tinker laning → jungle transition, driven by Dota 2's
Game State Integration (GSI). Rules and benchmarks come from 25 parsed
patch-7.41 replays (23 Immortal pubs + NothingToSay), the same data as
`Tinker_Farming_Study.pdf` and `Tinker_Jungle_Transition_Drills.pdf`.

## Setup (once)

1. `python coach.py --install`
   - writes `gamestate_integration_tinkercoach.cfg` into Dota's
     `game/dota/cfg/gamestate_integration/` folder
   - extracts the official minimap art from your Dota install (needs Pillow)
2. In Steam: Library → Dota 2 → Properties → Launch Options, add
   `-gamestateintegration` (keep your other options), then restart Dota.

## Every game

Double-click `run_coach.bat` (or `python coach.py`) and play. Dota must be in
**Borderless Window** mode (Settings → Video), otherwise nothing can draw over it.

What you see in game — both are transparent and click-through:

- **HUD** (above the minimap): the big letter is where your next Keen goes,
  `▶` is the one thing to press right now, `then` is the step after, plus the
  fountain stopwatch and the most urgent warning.
- **Minimap ring**: a pulsing circle on Dota's own minimap around the camps to go to next.

| Hotkey | |
|---|---|
| Ctrl+Alt+U | unlock/lock the overlays: drag them; on the minimap overlay mouse-wheel = size, arrows = nudge. Line the dots and the white fountain ring up with your minimap, then lock (saved to `settings.json`) |
| Ctrl+Alt+P | full panel (map, trips, checklist, benchmarks) |
| Ctrl+Alt+H | hide/show the overlays |
| Ctrl+Alt+Q | quit the coach (it runs without a console window, so closing cmd doesn't stop it) |

The overlays place themselves from your own Dota settings (`dota_hud_flip` and
`dota_hud_extra_large_minimap` in your Steam cloud config) and your screen size, using
the minimap sizes from Dota's HUD stylesheet. If it's still a few pixels off, press
Ctrl+Alt+U once and nudge it; a position you set by hand is remembered.

## The HUD

A frosted card above your minimap (real per-pixel transparency, still click-through):

- **Badge**: the station for your next Keen (A mid pair, B mid wave, C hard + ancient, D/E far camps, W side wave, F fountain)
- **NOW**: the one thing to press, with Dota's own ability icon, and **then** the step after
- **Pills**: fountain stopwatch, camp state ("March working…", "1 left", "camp clear"), last hits and net worth vs the Immortal median
- **Warning line**: the most urgent problem, red or amber

**Camp finisher.** About 4 s after each March (when most robots have hit), the coach counts the
neutrals still standing around you (Dota's minimap data) and swaps NOW for the fastest finish:
1 left and Laser ready → *Laser the last one*; more, or a big one → *Rearm → March*; none → *Keen*.
Right-clicking is never suggested: a March does ~10× Tinker's attack damage per second.

`python coach.py --install` also extracts the ability icons (`icons/`) and neutral creep stats
(`neutrals.json`) from your Dota files.

## Drill map: start from your saved 5:00 state (recommended)

A local Workshop custom game (needs the free *Dota 2 Workshop Tools* DLC, already installed here):

    python workshop.py save      # save your level, skills, items and gold at 5:00 from your latest recorded game
    play_drill.bat               # close Dota first; starts the coach and launches straight into the drill

Tinker on Radiant, no enemy heroes. The first 5 minutes run at 10x while you're held in
fountain (camps, waves and runes end up in their natural 5:00 state and the coach's benchmarks
line up), then at 4:55 your saved state is restored, you're refreshed, and you play until
10:00, when the drill ends. Every run lands on the score sheet like a normal game.

## Lobby drill (fallback): start at level 6, 5:00

1. `python coach.py --install` once (adds `cfg/tinker_drill.cfg` and binds **F11** to it in
   `autoexec.cfg`, in a marked block you can delete), then restart Dota.
2. Create a private lobby with **Enable cheats**, pick Tinker, and press **F11** once in game:
   the game starts, you're levelled to 6 with laning gold (`-lvlup 5`, `-gold 1800`), and the
   clock runs 10× (camps spawn and waves push normally). Spend your skill points and buy while it runs.
3. At ~4:55 the coach drops back to normal speed for you (it rewrites the cfg and presses F11,
   only while Dota is the focused window) and refreshes your cooldowns. Go: Keen → fountain → A.

The coach can tell a drill from a real game because the game clock runs faster than real time;
it never presses keys otherwise.

## Jev bot: watch Tinker farm 0:00 to 10:00

    play_bot.bat                     (= python bot.py) close Dota first
    python bot.py --advisor rules    same run with the built-in rules deciding, to compare with Jev
    python bot.py --speed 2          2x game speed · --end 1200 to play until 20:00

A Workshop custom game (`tinker_bot`, Radiant, no enemy heroes) where a script plays Tinker:
laning and last hits until level 6, then the Keen loop: Keen to a station, walk into the camp,
March, Rearm, March (turned 180°), watch, finish, Keen home, Rearm, refill, repeat. It buys
Branches, Tango, Faerie Fire, Bottle, Robe, Staff, Kaya, Blink as gold allows (in fountain once it has Keen).

What code does vs what Jev decides:

- **Code**: everything timing- or arithmetic-based (walking, last hits, aiming, channel waits, buying, and the
  facts: what has respawned, creeps' HP, whether a Laser kills the last one, mana after another March).
- **Jev** (through `bot.py`'s local bridge): where to Keen next (A/C/D, mid wave, fountain) and how to finish a
  camp (Laser, Rearm + March, right-click, or leave). A wave at your tower is always taken (hard rule). If Jev is
  unsure (confidence < 0.35), slower than 1.5 s, or unreachable, the built-in rule decides.

Type `-bot` in chat to take control yourself, `-bot` again to hand it back.

**Video + thinking panel.** While the bot plays, a transparent panel (top right) shows what it is doing now,
the last decision (every option with Jev's probability, the pick, what the rules would have picked, and the
facts Jev was given), net worth against your best laned run, and the trip log. With `--video` the whole
screen, panel included, is filmed from 0:00 to the result card into `bot_runs/<date_time>.mp4` (off by
default, ~300 MB a run; needs ffmpeg, GPU encoder when available). With OBS instead: use a *Display Capture*
source, since Game Capture doesn't include overlays.
Everything is recorded to `bot_runs/<date_time>.jsonl` (a snapshot every second plus every Keen, cast, buy,
decision and Jev's probabilities); each run adds a line to `bot_runs/summary.csv`. Bot runs never touch your
`runs.csv` or score sheet. Cost: one Jev decision is ~1,000 input tokens ($0.042 per 1M), well under a cent a run.

## Waves and March level

- Only the **mid** wave counts (side lanes are your teammates'). From the GSI `minimap` block the
  coach sees enemy creeps: a mid wave pushed past your tier-1 (or at your tier-2) becomes the NEXT
  station (B) with a ring on the wave; otherwise a mid wave on your half fills the gap while camps
  respawn (never two waves in a row). Keening to a side lane gets a written note.
- The ancients (C) are only suggested once March of the Machines is level 4. With March
  below level 3, camp plans get a third March.

After 10:00 a row is added to `scoresheet.csv` (same score sheet as the drill guide).

## Net worth and your training log

GSI doesn't report net worth to players, so the coach computes it: your gold plus the
price of everything in your inventory, backpack and stash (current-patch prices from
your Dota files, `item_costs.json`). The HUD shows it next to last hits, both against the
Immortal median for that minute.

Every run is logged automatically:

- `runs.csv`: one row per game minute (LH, net worth and gap to the Immortal median,
  gold, GPM, XPM, level, camp trips, fountain stops, items)
- `scoresheet.csv`: one row per run at 10:00 (the drill-guide checkpoints)
- `sessions/<date_time>.jsonl`: the raw game state, 4 times a second, for trip-by-trip review

`python stats.py` turns them into `stats.html` (opens in your browser): every run against
the drill targets, plus net-worth and last-hit curves against the benchmarks.

## Options

    python coach.py --port 3099         listen on another port (the .cfg must match)
    python coach.py --no-record         don't save the session (by default every session goes to
                                        sessions/<date_time>.jsonl, 4 updates/s, for trip-by-trip review)
    python simulate.py samples/you_9016088490.jsonl --speed 4 --start 300
                                        replay a game into a running coach

`samples/` holds your match and the two model games (Radiant 9020212922,
Dire 9020204172), rebuilt as GSI messages from their replays.

## Limits

GSI only exposes your own hero, so the coach can't see creeps or camp states.
Camp kills are inferred from last hits gained while standing at a camp (3+ in
one visit), and respawns from the minute timer. Rearm is detected from its mana
cost in fountain and from Keen Teleport's cooldown being wiped.
