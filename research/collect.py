"""Collect recent high-rank Tinker replays: find players, list their mid Tinker games, download -> parse -> delete.

    python collect.py list [N]      build data/collect_queue.json (up to N matches with a replay URL)
    python collect.py run           download, parse (NeutralHP + Extract) and delete each replay
"""
import bz2, concurrent.futures as cf, json, os, subprocess, sys, time, urllib.request
from compression import zstd
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "data"); Q = os.path.join(D, "collect_queue.json")
J = r"C:/Program Files/Java/jdk-26.0.2/bin/java"
UA = {"User-Agent": "Mozilla/5.0 tinker-coach research"}


def od(path):
    for i in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request("https://api.opendota.com/api/" + path, headers=UA), timeout=40))
        except Exception as ex:
            if "429" in str(ex): time.sleep(20)
            else: time.sleep(2)
    return None


def have():
    got = {f.split("_")[0][1:] for f in os.listdir(os.path.join(D, "nhp")) if f.endswith("_neu.csv")}
    got |= {f[1:-4] for f in os.listdir(os.path.join(HERE, "replays")) if f.endswith(".dem") and f[0] in "ps"}
    return got


def build_list(n):
    ranks = od("rankings?hero_id=34") or {}
    players = [r["account_id"] for r in ranks.get("rankings", [])][:120]
    extra = json.load(open(os.path.join(D, "stratz_players.json"))) if os.path.exists(os.path.join(D, "stratz_players.json")) else []
    players = list(dict.fromkeys(extra + players))
    print(len(players), "players")
    seen, cands = have(), []
    for i, a in enumerate(players):
        ms = od(f"players/{a}/matches?hero_id=34&date=14&lane_role=2&significant=1") or []
        for m in ms:
            if m.get("duration", 0) >= 1100 and str(m["match_id"]) not in seen and m["match_id"] not in {c["match"] for c in cands}:
                cands.append({"match": m["match_id"], "acc": a, "start": m.get("start_time"), "rank": m.get("average_rank")})
        time.sleep(1.1)
        if i % 10 == 0: print(f"  {i}/{len(players)} players, {len(cands)} candidate games")
    cands.sort(key=lambda c: -(c["start"] or 0))
    queue = []
    for c in cands:
        if len(queue) >= n: break
        m = od(f"matches/{c['match']}")
        time.sleep(1.1)
        if m and m.get("replay_url"):
            c["url"] = m["replay_url"]; c["patch"] = m.get("patch"); queue.append(c)
    json.dump(queue, open(Q, "w"))
    print(len(queue), "games queued with a replay URL")


def one(c):
    mid = c["match"]; dem = os.path.join(HERE, "replays", f"c{mid}.dem"); pre = os.path.join(D, "nhp", f"c{mid}")
    if os.path.exists(pre + "_neu.csv"): return mid, "done before"
    try:
        raw = urllib.request.urlopen(urllib.request.Request(c["url"], headers=UA), timeout=180).read()
        data = zstd.decompress(raw) if raw[:4] == b"\x28\xb5\x2f\xfd" else bz2.decompress(raw)
        if not data.startswith(b"PBDEMS2"): return mid, "not a replay"
        open(dem, "wb").write(data)
        cp = "out;lib/*"
        r1 = subprocess.run([J, "--enable-native-access=ALL-UNNAMED", "-cp", cp, "NeutralHP", dem, pre], cwd=HERE, capture_output=True, timeout=900)
        r2 = subprocess.run([J, "--enable-native-access=ALL-UNNAMED", "-cp", cp, "Extract", dem, os.path.join(D, f"c{mid}")], cwd=HERE, capture_output=True, timeout=900)
        ok = os.path.exists(pre + "_neu.csv") and os.path.getsize(pre + "_neu.csv") > 1000
        return mid, f"parsed ({len(data)/1e6:.0f} MB)" if ok else f"parse failed {r1.stderr[-200:]}"
    except Exception as ex:
        return mid, f"failed: {type(ex).__name__} {ex}"
    finally:
        if os.path.exists(dem): os.remove(dem)                      # free the space right away


def run():
    queue = json.load(open(Q))
    ok = 0
    with cf.ThreadPoolExecutor(4) as ex:
        for mid, res in ex.map(one, queue):
            ok += res.startswith("parsed") or res == "done before"
            print(mid, res, flush=True)
    print(f"{ok}/{len(queue)} games parsed")


if __name__ == "__main__":
    if sys.argv[1] == "list": build_list(int(sys.argv[2]) if len(sys.argv) > 2 else 150)
    else: run()
