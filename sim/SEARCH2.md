```
bot: 2379

start: bot
  round 0: L3_A   -> False       2414 (+43)
  round 0: order  -> ABCBDBC     2451 (+37)
  round 0: B_N    -> 3           2559 (+108)
  round 0: N4_D   -> 2           2627 (+67)
  round 1: N3_D   -> 4           2651 (+24)
  round 1: order  -> ABDBCB      2731 (+80)
  round 1: X      -> 360         2779 (+48)
  -> 2779

start: fewer Marches
  round 0: order  -> ABDBCB      2423 (+82)
  round 0: B_N    -> 3           2645 (+222)
  round 1: X      -> 360         2679 (+34)
  round 1: N4_C   -> 3           2732 (+53)
  round 2: N3_D   -> 4           2771 (+39)
  -> 2771

start: ABCBDB cycle
  round 0: N3_D   -> 4           2471 (+26)
  round 0: B_N    -> 3           2668 (+197)
  round 0: N4_D   -> 2           2713 (+45)
  round 1: X      -> 300         2746 (+33)
  -> 2746

start: random
  round 0: L3_D   -> True        2171 (+70)
  round 0: L3_A   -> True        2215 (+44)
  round 0: N4_A   -> 2           2362 (+148)
  round 0: X      -> 600         2442 (+80)
  round 0: order  -> ABDBCB      2639 (+196)
  -> 2639

re-scored on fresh seeds (1000+, 1200 games):
from bot                  2777  sd  267  LH  76.5  trips 14.5  home  94.8 s  mana-out  492  d vs bot +394 +/- 21
from fewer Marches        2737  sd  273  LH  74.5  trips 14.4  home  94.3 s  mana-out  479  d vs bot +354 +/- 21
from ABCBDB cycle         2733  sd  257  LH  74.8  trips 14.7  home  92.9 s  mana-out  451  d vs bot +350 +/- 19
from random               2623  sd  299  LH  69.8  trips 12.5  home  97.4 s  mana-out  648  d vs bot +240 +/- 22
```
