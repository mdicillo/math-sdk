"""Stake's volatility gate per mode, normalized the way the platform applies it (docs/STAKE_PORT.md in the game repo,
"The volatility gate"): the SDK's local check (utils/rgs_verification.verify_mode_volatility) compares raw values, so a
pricey mode prints violations the platform does not gate on. Here, from the published lookup tables:

  rtp      the table's return / cost                                                   (limit 0.967)
  cvar     average of the top 0.1% of wins, as a multiple of the cost                    (limit 800)
  etl40b   share of the return from wins >= 40 x cost                                    (limit 0.9)
  etl10k   share of the return from wins >= 10,000x the base bet (the SDK's threshold)    (limit 0.8)
  prob5k   chance of a win >= 5,000x the base bet (the SDK's threshold, scaled as it does) (limit 1%)

Run: PYTHONPATH=. python3 games/sheriff_showdown/volatility.py
"""

import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", ".."))

from utils.analysis.distribution_functions import conditional_value_at_risk, get_prob_scale  # noqa: E402

LIMITS = {"rtp": 0.967, "cvar": 800, "etl40b": 0.9, "etl10k": 0.8, "prob5k": 0.01}


def mode_stats(mode: str, cost: float) -> dict:
    dist = {}
    path = os.path.join(HERE, "library", "publish_files", f"lookUpTable_{mode}_0.csv")
    with open(path, encoding="UTF-8") as f:
        for row in csv.reader(f):
            win = int(row[2]) / 100
            dist[win] = dist.get(win, 0) + int(row[1])
    total = sum(dist.values())
    ret = sum(w * c for w, c in dist.items()) / total
    return {
        "rtp": ret / cost,
        "cvar": conditional_value_at_risk(0.999, dist, total) / cost,
        "etl40b": sum(w * c for w, c in dist.items() if w >= 40 * cost) / total / ret,
        "etl10k": sum(w * c for w, c in dist.items() if w >= 10_000) / total / ret,
        "prob5k": sum(c for w, c in dist.items() if w >= 5_000) / total * get_prob_scale(cost),
        "max_win_one_in": total / dist.get(max(dist), 1),
    }


def main() -> None:
    with open(os.path.join(HERE, "targets.json"), encoding="UTF-8") as f:
        modes = {m: v["cost"] for m, v in json.load(f)["modes"].items()}
    out = {}
    for mode, cost in modes.items():
        s = mode_stats(mode, cost)
        bad = [k for k, lim in LIMITS.items() if s[k] > lim]
        out[mode] = {**s, "violations": bad}
        print(f"{mode:18s} rtp {s['rtp'] * 100:.4f}%  cvar {s['cvar']:8.2f}  etl40b {s['etl40b']:.4f}  etl10k {s['etl10k']:.4f}  "
              f"prob5k {s['prob5k']:.6f}  max win 1 in {s['max_win_one_in']:,.0f}  {'PASS' if not bad else 'FAIL ' + ','.join(bad)}")
    with open(os.path.join(HERE, "library", "volatility_report.json"), "w", encoding="UTF-8") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    main()
