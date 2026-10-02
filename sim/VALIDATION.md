# Validation: the bot's lab_10x policy in the simulator vs the real runs

real = 95 lab_10x games (mean, run-to-run sd); sim = 600 simulated games. z = (sim mean - real mean) / real sd; |z| < 1 means the simulator mean is inside the real spread.

| metric | real mean | real sd | sim mean | sim sd | z |
|---|---|---|---|---|---|
| gold gained 5:00-10:00 (nw) | 2427.7 | 185.9 | 2441.2 | 222.9 | +0.07 |
| last hits | 67.3 | 7.3 | 68.2 | 8.4 | +0.12 |
| trips | 14.4 | 0.5 | 14.7 | 0.6 | +0.56 |
| camp trips | 9.9 | 0.9 | 10.2 | 0.9 | +0.37 |
| wave (B) trips | 4.6 | 1.0 | 4.5 | 1.1 | -0.04 |
| seconds going home (sum) | 100.6 | 4.5 | 97.1 | 4.5 | -0.76 |
| fountain stop (s, landing->Keen out) | 4.0 | 0.3 | 3.9 | 0.3 | -0.22 |
| mana at Keen home order (mean per run) | 380.5 | 49.1 | 370.7 | 63.5 | -0.20 |
| mana at Keen out order (mean per run) | 567.4 | 35.5 | 558.6 | 50.7 | -0.25 |
| gold gained by 6:00 | 479.7 | 75.2 | 467.0 | 101.5 | -0.17 |
| gold gained by 7:00 | 965.3 | 108.5 | 923.4 | 134.9 | -0.39 |
| gold gained by 8:00 | 1456.0 | 140.2 | 1439.2 | 163.7 | -0.12 |
| gold gained by 9:00 | 1947.8 | 158.1 | 1931.8 | 197.0 | -0.10 |
| gold gained by 10:00 | 2424.3 | 186.0 | 2419.0 | 221.5 | -0.03 |
| trips to A | 4.0 | 1.4 | 3.8 | 1.7 | -0.14 |
| trips to B | 4.6 | 1.0 | 4.5 | 1.1 | -0.04 |
| trips to C | 1.5 | 0.7 | 1.7 | 0.9 | +0.27 |
| trips to D | 3.3 | 1.0 | 3.6 | 1.2 | +0.30 |
| trips to E | 1.0 | 0.0 | 1.0 | 0.2 | +0.00 |
| LH per trip at A | 4.8 | 1.1 | 4.8 | 1.2 | +0.00 |
| LH per trip at B | 3.3 | 0.8 | 3.3 | 0.8 | -0.02 |
| LH per trip at C | 5.6 | 1.4 | 5.9 | 1.8 | +0.26 |
| LH per trip at D | 6.2 | 1.2 | 6.0 | 1.5 | -0.14 |
| LH per trip at E | 5.7 | 1.3 | 5.7 | 1.3 | -0.04 |

Mana at each Keen-home order (all orders pooled), quantiles 10/25/50/75/90:
- real: [194, 259, 373, 487, 605] (n=1337, mean 382)
- sim:  [182, 252, 367, 477, 587] (n=8314, mean 372)

Mana at each Keen-out order (leaving the fountain), quantiles 10/25/50/75/90:
- real: [403, 443, 524, 671, 829] (mean 568)
- sim:  [430, 436, 495, 650, 843] (mean 559)

rows outside |z|<1: 0 of 24

## Hold-out check

Payoff samples rebuilt without the other half... (payoffs from the odd-numbered lab_10x games removed, compared on those games)

real = 47 lab_10x games (mean, run-to-run sd); sim = 600 simulated games. z = (sim mean - real mean) / real sd; |z| < 1 means the simulator mean is inside the real spread.

| metric | real mean | real sd | sim mean | sim sd | z |
|---|---|---|---|---|---|
| gold gained 5:00-10:00 (nw) | 2413.8 | 172.6 | 2452.0 | 246.2 | +0.22 |
| last hits | 67.0 | 7.4 | 69.2 | 8.8 | +0.30 |
| trips | 14.4 | 0.6 | 14.8 | 0.6 | +0.58 |
| camp trips | 9.9 | 0.9 | 10.2 | 1.0 | +0.33 |
| wave (B) trips | 4.5 | 1.0 | 4.6 | 1.1 | +0.05 |
| seconds going home (sum) | 101.3 | 4.9 | 96.7 | 4.7 | -0.93 |
| fountain stop (s, landing->Keen out) | 4.0 | 0.3 | 3.9 | 0.3 | -0.34 |
| mana at Keen home order (mean per run) | 375.9 | 54.5 | 371.6 | 62.7 | -0.08 |
| mana at Keen out order (mean per run) | 565.5 | 37.4 | 559.4 | 51.7 | -0.16 |
| gold gained by 6:00 | 473.1 | 72.6 | 470.2 | 106.2 | -0.04 |
| gold gained by 7:00 | 954.1 | 95.6 | 939.1 | 139.0 | -0.16 |
| gold gained by 8:00 | 1443.9 | 139.4 | 1458.5 | 180.7 | +0.11 |
| gold gained by 9:00 | 1944.2 | 147.3 | 1950.2 | 218.1 | +0.04 |
| gold gained by 10:00 | 2409.0 | 171.8 | 2435.5 | 245.7 | +0.15 |
| trips to A | 4.0 | 1.5 | 3.8 | 1.7 | -0.08 |
| trips to B | 4.5 | 1.0 | 4.6 | 1.1 | +0.05 |
| trips to C | 1.6 | 0.8 | 1.7 | 0.9 | +0.18 |
| trips to D | 3.4 | 1.0 | 3.6 | 1.2 | +0.22 |
| trips to E | 1.0 | 0.0 | 1.0 | 0.2 | +0.00 |
| LH per trip at A | 4.8 | 1.2 | 4.9 | 1.3 | +0.16 |
| LH per trip at B | 3.3 | 0.8 | 3.4 | 0.8 | +0.10 |
| LH per trip at C | 5.7 | 1.6 | 5.8 | 1.9 | +0.10 |
| LH per trip at D | 6.1 | 1.2 | 6.0 | 1.5 | -0.11 |
| LH per trip at E | 5.6 | 1.2 | 5.8 | 1.4 | +0.12 |

Mana at each Keen-home order (all orders pooled), quantiles 10/25/50/75/90:
- real: [188, 254, 359, 487, 605] (n=661, mean 377)
- sim:  [186, 256, 365, 473, 590] (n=8295, mean 372)

Mana at each Keen-out order (leaving the fountain), quantiles 10/25/50/75/90:
- real: [403, 442, 516, 671, 838] (mean 566)
- sim:  [431, 436, 496, 650, 843] (mean 560)

rows outside |z|<1: 0 of 24
