# Replay research

Code behind the numbers the coach and the bot use (Clarity 4.0.2 replay parser, Java 26, Python 3.14).

- `src/Extract.java`: Tinker snapshots, combat log events, unit deaths, spawns, heroes per replay
- `src/MarchDirs.java`: every March with Tinker's position and facing
- `src/NeutralHP.java`: neutral creep HP around Tinker (every 0.2 s), casts, spawns/removals, mid-lane creeps, heroes
- `src/Buys.java`: item purchases
- `collect.py`: find recent high-rank Tinker games (OpenDota), download -> parse -> delete
- `metrics.py`, `transition.py`: trips, farm metrics per game
- `nhp_camps.py`, `nhp_report.py`: March effectiveness per camp (148 games, 1,098 camp trips)
- `jev_dataset.py`: Immortal "where next" decisions for scoring Jev
- `respawn_check2.py`: shows 7.41 camps spawn into camps that still hold creeps

Compile: `javac -cp "lib/*" -d out src/*.java` with the Clarity jars in `lib/`.
