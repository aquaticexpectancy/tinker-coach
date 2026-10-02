# Validation: the bot's lab_10x policy in the simulator vs the real runs

real = 95 lab_10x games (mean, run-to-run sd); sim = 600 simulated games. z = (sim mean - real mean) / real sd; |z| < 1 means the simulator mean is inside the real spread.

| metric | real mean | real sd | sim mean | sim sd | z |
|---|---|---|---|---|---|
| gold gained 5:00-10:00 (nw) | 2427.7 | 185.9 | 2395.7 | 226.9 | -0.17 |
| last hits | 67.3 | 7.3 | 67.6 | 8.1 | +0.04 |
| trips | 14.4 | 0.5 | 14.6 | 0.6 | +0.32 |
| camp trips | 9.9 | 0.9 | 10.3 | 1.0 | +0.42 |
| wave (B) trips | 4.6 | 1.0 | 4.3 | 1.2 | -0.21 |
| seconds going home (sum) | 100.6 | 4.5 | 96.3 | 4.6 | -0.94 |
| fountain stop (s, landing->Keen out) | 4.0 | 0.3 | 3.9 | 0.3 | -0.22 |
| mana at Keen home order (mean per run) | 380.5 | 49.1 | 367.4 | 63.1 | -0.27 |
| mana at Keen out order (mean per run) | 567.4 | 35.5 | 555.5 | 48.4 | -0.34 |
| gold gained by 6:00 | 479.7 | 75.2 | 426.3 | 101.4 | -0.71 |
| gold gained by 7:00 | 965.3 | 108.5 | 906.3 | 137.0 | -0.54 |
| gold gained by 8:00 | 1456.0 | 140.2 | 1418.0 | 169.4 | -0.27 |
| gold gained by 9:00 | 1947.8 | 158.1 | 1906.2 | 199.7 | -0.26 |
| gold gained by 10:00 | 2424.3 | 186.0 | 2379.8 | 228.0 | -0.24 |
| trips to A | 4.0 | 1.4 | 3.9 | 1.7 | -0.11 |
| trips to B | 4.6 | 1.0 | 4.3 | 1.2 | -0.21 |
| trips to C | 1.5 | 0.7 | 1.8 | 1.0 | +0.42 |
| trips to D | 3.3 | 1.0 | 3.6 | 1.1 | +0.22 |
| trips to E | 1.0 | 0.0 | 1.0 | 0.2 | +0.00 |
| LH per trip at A | 4.8 | 1.1 | 4.9 | 1.3 | +0.15 |
| LH per trip at B | 3.3 | 0.8 | 3.2 | 0.8 | -0.17 |
| LH per trip at C | 5.6 | 1.4 | 5.9 | 1.8 | +0.22 |
| LH per trip at D | 6.2 | 1.2 | 6.1 | 1.4 | -0.05 |
| LH per trip at E | 5.7 | 1.3 | 5.1 | 1.3 | -0.50 |

Mana at each Keen-home order (all orders pooled), quantiles 10/25/50/75/90:
- real: [194, 259, 373, 487, 605] (n=1337, mean 382)
- sim:  [177, 248, 359, 471, 585] (n=8231, mean 368)

Mana at each Keen-out order (leaving the fountain), quantiles 10/25/50/75/90:
- real: [403, 443, 524, 671, 829] (mean 568)
- sim:  [430, 436, 495, 642, 840] (mean 556)

rows outside |z|<1: 0 of 24
