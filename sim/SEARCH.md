```
BASELINE (the bot, lab plan, fountain after every trip):    2371  sd  226  LH  67.0  trips 14.6  home  96.5 s  mana-out  548

== stage 1: one-dimensional sweeps from the bot ==
X=300         2393  sd  222  LH  67.5  trips 14.8  home  94.0 s  mana-out  487  d vs bot    +22 +/-  28
X=360         2381  sd  226  LH  67.3  trips 14.7  home  95.5 s  mana-out  511  d vs bot    +10 +/-  23
X=420         2371  sd  228  LH  66.8  trips 14.6  home  96.7 s  mana-out  546  d vs bot     +1 +/-  10
X=480         2355  sd  231  LH  66.5  trips 14.5  home  96.9 s  mana-out  581  d vs bot    -15 +/-  22
X=540         2375  sd  226  LH  67.5  trips 14.5  home  97.3 s  mana-out  623  d vs bot     +5 +/-  25
X=600         2348  sd  213  LH  66.3  trips 14.4  home  97.6 s  mana-out  664  d vs bot    -22 +/-  28
X=660         2340  sd  222  LH  65.9  trips 14.3  home  99.2 s  mana-out  702  d vs bot    -30 +/-  32
X=720         2294  sd  211  LH  64.2  trips 14.0  home 102.3 s  mana-out  741  d vs bot    -76 +/-  32
X=780         2266  sd  195  LH  64.1  trips 13.7  home 106.5 s  mana-out  787  d vs bot   -105 +/-  32
X=840         2198  sd  195  LH  61.7  trips 13.3  home 111.9 s  mana-out  832  d vs bot   -172 +/-  30
chain+-100    2387  sd  214  LH  67.1  trips 14.8  home  93.8 s  mana-out  527  d vs bot    +17 +/-  33
chain+0       2389  sd  220  LH  67.4  trips 14.7  home  95.6 s  mana-out  541  d vs bot    +18 +/-  34
chain+100     2379  sd  220  LH  67.2  trips 14.6  home  97.3 s  mana-out  554  d vs bot     +8 +/-  34
chain+200     2376  sd  220  LH  67.1  trips 14.6  home  98.0 s  mana-out  558  d vs bot     +5 +/-  34
chain+300     2375  sd  223  LH  67.0  trips 14.6  home  98.3 s  mana-out  560  d vs bot     +4 +/-  34
chain+400     2375  sd  221  LH  67.0  trips 14.6  home  98.5 s  mana-out  560  d vs bot     +5 +/-  34
chain+600     2375  sd  221  LH  67.0  trips 14.6  home  98.6 s  mana-out  560  d vs bot     +5 +/-  34

== stage 2: every March-count vector ==
ml4 (March 4, 7:00 on): best 8 of 1024
ml4 N=(2, 4, 3, 2) L(A,D)=(False, True)    2388  sd  231  LH  66.3  trips 14.6  home  95.5 s  mana-out  560  d vs bot    +17 +/-  27
ml4 N=(2, 4, 3, 3) L(A,D)=(False, True)    2388  sd  231  LH  66.3  trips 14.6  home  95.5 s  mana-out  560  d vs bot    +17 +/-  28
ml4 N=(2, 4, 3, 4) L(A,D)=(False, True)    2387  sd  231  LH  66.3  trips 14.6  home  95.5 s  mana-out  560  d vs bot    +17 +/-  27
ml4 N=(2, 4, 3, 1) L(A,D)=(False, True)    2387  sd  231  LH  66.2  trips 14.6  home  95.6 s  mana-out  560  d vs bot    +16 +/-  27
ml4 N=(2, 4, 3, 2) L(A,D)=(True, True)    2382  sd  225  LH  66.8  trips 14.4  home  95.2 s  mana-out  547  d vs bot    +12 +/-  21
ml4 N=(2, 4, 3, 3) L(A,D)=(True, True)    2382  sd  226  LH  66.8  trips 14.4  home  95.2 s  mana-out  547  d vs bot    +12 +/-  21
ml4 N=(2, 4, 3, 4) L(A,D)=(True, True)    2382  sd  226  LH  66.8  trips 14.4  home  95.2 s  mana-out  547  d vs bot    +11 +/-  21
ml4 N=(2, 4, 3, 1) L(A,D)=(True, True)    2380  sd  225  LH  66.7  trips 14.4  home  95.3 s  mana-out  547  d vs bot    +10 +/-  21
ml3 (March 3, until ~6:12): best 5 of 64
ml3 N(A,D,E)=(3, 3, 4)                2415  sd  221  LH  69.0  trips 14.3  home  96.2 s  mana-out  552  d vs bot    +44 +/-  31
ml3 N(A,D,E)=(3, 4, 4)                2412  sd  221  LH  68.7  trips 14.4  home  96.0 s  mana-out  552  d vs bot    +42 +/-  31
ml3 N(A,D,E)=(4, 3, 4)                2411  sd  224  LH  69.0  trips 14.3  home  95.4 s  mana-out  554  d vs bot    +41 +/-  34
ml3 N(A,D,E)=(4, 4, 4)                2411  sd  224  LH  69.0  trips 14.4  home  95.3 s  mana-out  554  d vs bot    +40 +/-  34
ml3 N(A,D,E)=(4, 4, 3)                2404  sd  239  LH  67.5  trips 14.6  home  95.6 s  mana-out  550  d vs bot    +33 +/-  25

== stage 3: fountain threshold x chaining x routing on the best counts ==
X=500 chain=0                 2424  sd  246  LH  67.4  trips 14.2  home  95.0 s  mana-out  597  d vs bot    +54 +/-  34
X=500 chain=150               2419  sd  242  LH  67.5  trips 14.1  home  97.4 s  mana-out  615  d vs bot    +48 +/-  35
X=bot chain=0                 2417  sd  238  LH  67.9  trips 14.5  home  94.5 s  mana-out  542  d vs bot    +47 +/-  36
X=500 chain=300               2414  sd  237  LH  67.5  trips 14.0  home  98.4 s  mana-out  619  d vs bot    +43 +/-  35
X=400 chain=0                 2412  sd  234  LH  67.8  trips 14.5  home  94.7 s  mana-out  532  d vs bot    +41 +/-  37
X=600 chain=0                 2412  sd  230  LH  66.4  trips 14.1  home  95.9 s  mana-out  652  d vs bot    +41 +/-  36
X=500 chain=None              2409  sd  240  LH  67.2  trips 14.1  home  96.3 s  mana-out  613  d vs bot    +39 +/-  33
X=bot chain=150               2406  sd  235  LH  67.7  trips 14.4  home  97.0 s  mana-out  564  d vs bot    +36 +/-  35
X=400 chain=150               2405  sd  236  LH  67.6  trips 14.4  home  96.7 s  mana-out  549  d vs bot    +34 +/-  36
X=400 chain=300               2402  sd  232  LH  67.5  trips 14.3  home  97.5 s  mana-out  551  d vs bot    +32 +/-  37

fixed station cycles (654 sequences of length 3-7 over A,B,C,D, B taken only when a wave is up) with the best knobs:
cycle ABCBDCB                 2480  sd  289  LH  67.1  trips 13.6  home  94.2 s  mana-out  567  d vs bot   +100 +/-  72
cycle ABCBDB                  2462  sd  249  LH  68.1  trips 14.3  home  96.7 s  mana-out  576  d vs bot    +82 +/-  65
cycle ABDBCB                  2446  sd  241  LH  67.4  trips 14.3  home  96.4 s  mana-out  585  d vs bot    +66 +/-  69
cycle ABCDBAB                 2441  sd  208  LH  68.1  trips 14.6  home  94.0 s  mana-out  579  d vs bot    +61 +/-  60
cycle ABDCBDB                 2435  sd  218  LH  68.7  trips 14.2  home  96.2 s  mana-out  581  d vs bot    +55 +/-  64
cycle ABDBACB                 2432  sd  248  LH  67.5  trips 14.8  home  95.4 s  mana-out  595  d vs bot    +52 +/-  65
cycle ACBDB                   2430  sd  244  LH  67.1  trips 14.1  home  94.9 s  mana-out  575  d vs bot    +50 +/-  67
cycle ABDABCB                 2428  sd  229  LH  66.6  trips 14.7  home  96.0 s  mana-out  594  d vs bot    +48 +/-  67

== stage 4: winners re-scored on fresh seeds (1000+) ==
bot                               2396  sd  227  LH  67.6  trips 14.6  home  96.3 s  mana-out  556  d vs bot     +0 +/-   0
best counts only                  2389  sd  232  LH  66.9  trips 14.4  home  95.6 s  mana-out  563  d vs bot     -6 +/-  24
X=500 chain=0                     2414  sd  236  LH  67.3  trips 14.2  home  95.1 s  mana-out  597  d vs bot    +19 +/-  24
cycle ABCBDCB                     2404  sd  264  LH  65.8  trips 13.6  home  94.5 s  mana-out  569  d vs bot     +8 +/-  27
X=500 chain=150                   2403  sd  224  LH  67.2  trips 14.1  home  97.4 s  mana-out  615  d vs bot     +8 +/-  24
X=bot chain=0                     2408  sd  232  LH  67.2  trips 14.4  home  94.4 s  mana-out  543  d vs bot    +12 +/-  24
X=500 chain=300                   2400  sd  222  LH  67.1  trips 14.0  home  98.2 s  mana-out  619  d vs bot     +5 +/-  24
```
