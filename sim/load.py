"""Shared loader for the Tinker offline simulator: reads bot_runs/*.jsonl and the batch CSVs."""
import csv, glob, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # tinker_coach
RUNS = os.path.join(ROOT, "bot_runs")


def batch_index():
    """{run file name: setup} from every bot_runs/batch_*.csv (status ok only)."""
    idx = {}
    for f in sorted(glob.glob(os.path.join(RUNS, "batch_*.csv"))):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if r.get("status") == "ok":
                idx[r["run"]] = r["setup"]
    return idx


def read_run(name):
    path = name if os.path.isabs(name) else os.path.join(RUNS, name)
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def runs_of(setup):
    return [n for n, s in batch_index().items() if s == setup]
