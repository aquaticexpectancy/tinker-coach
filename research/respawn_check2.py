import csv, glob, collections, math, bisect
res = collections.Counter(); sizes = collections.Counter()
for f in glob.glob("data/nhp/*_neu.csv"):
    g = f[:-8]
    neu = []
    for r in csv.DictReader(open(f, encoding="utf-8")):
        try: neu.append((float(r["clock"]), r["idx"], int(r["hp"]), float(r["x"]), float(r["y"])))
        except: pass
    by = collections.defaultdict(list)
    for t, i, hp, x, y in neu: by[t].append((i, hp, x, y))
    times = sorted(by)
    if not times: continue
    spawns = []
    for r in csv.DictReader(open(g + "_spawn.csv", encoding="utf-8")):
        try:
            if r["name"] != "gone": spawns.append((float(r["clock"]), r["idx"], float(r["x"]), float(r["y"])))
        except: pass
    for m in range(5, 20):
        t0 = m * 60
        batch = [s for s in spawns if 0 <= s[0] - t0 < 1.5]
        groups = []
        for s in batch:
            for gr in groups:
                if math.hypot(gr[0][2] - s[2], gr[0][3] - s[3]) < 500: gr.append(s); break
            else: groups.append([s])
        k = bisect.bisect_left(times, t0 - 1.2)
        if k >= len(times) or times[k] > t0: continue
        tb = times[k]
        for gr in groups:
            cx = sum(s[2] for s in gr) / len(gr); cy = sum(s[3] for s in gr) / len(gr)
            old = [hp for i, hp, x, y in by[tb] if hp > 0 and math.hypot(x - cx, y - cy) < 400]
            if old:
                res["new creeps spawned into a camp that still had living creeps"] += 1
                sizes[len(old) + len(gr)] += 1
    # (camps with sampled living creeps that did NOT get a spawn can't be told apart from unsampled ones here)
print(res)
print("camp size right after such a spawn (old + new creeps):", sorted(sizes.items()))
