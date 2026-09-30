"""Replay a recorded game into a running coach, as if Dota were sending it.

    python simulate.py samples/you_9016088490.jsonl --speed 4
    python simulate.py my_recording.jsonl            (made with coach.py --record)
"""
import argparse, json, time, urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("file")
ap.add_argument("--speed", type=float, default=4.0, help="game seconds per real second")
ap.add_argument("--start", type=float, default=0, help="skip to this game clock (seconds)")
ap.add_argument("--port", type=int, default=3031)
a = ap.parse_args()

rows = [json.loads(l) for l in open(a.file, encoding="utf-8")]
# samples store the game clock as "c"; live recordings store wall time as "t"
key = "c" if "c" in rows[0] else "t"
rows = [r for r in rows if key == "t" or r["c"] >= a.start]
t0, w0 = rows[0][key], time.time()
for r in rows:
    wait = (r[key] - t0) / a.speed - (time.time() - w0)
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(f"http://127.0.0.1:{a.port}/", data=json.dumps(r["p"]).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=5).read()
print("done")
