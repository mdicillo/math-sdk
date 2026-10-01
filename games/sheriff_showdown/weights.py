"""Published weights (user decision 2026-09-30: from the spec's exact probabilities, tuned within each category only
enough to land 96.00%). Replaces the SDK optimizer for this game.

For every mode, each category (categories.py) gets exactly its probability. Inside a category the books' weights are
the least change from equal (minimum relative entropy) that brings the category's average to its target:
w_i proportional to exp(lambda x payout_i), lambda solved; categories whose books all pay the same (a paid Showdown
outcome, an X5000 round at the cap) keep equal weights. Weights are integers summing to 2^50 (the SDK optimizer's
scale), so the lookup table's RTP is 96.00% to rounding.

Reads library/lookup_tables/lookUpTable_<mode>.csv (book, weight, payout) and lookUpTableSegmented_<mode>.csv (book,
criteria, ...); writes library/publish_files/lookUpTable_<mode>_0.csv and weights_report.json.
"""

import csv
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from categories import categories  # noqa: E402

TOTAL_WEIGHT = 2**50
LIBRARY = os.path.join(HERE, "library")


def tilt(payouts: list, target: float) -> list:
    """Weights (summing to 1) for payouts with weighted average `target`: w_i ~ exp(lam x_i), the least change from
    equal weights. Equal weights when every payout is the same."""
    lo_x, hi_x = min(payouts), max(payouts)
    n = len(payouts)
    if hi_x - lo_x < 1e-12:
        assert abs(lo_x - target) < 1e-6 * max(1.0, abs(target)), (lo_x, target)
        return [1 / n] * n
    assert lo_x < target < hi_x, f"target {target} outside the books' range {lo_x}..{hi_x}"
    scale = hi_x - lo_x

    def mean(lam: float) -> float:
        z = [lam * (x - hi_x) / scale for x in payouts]
        m = max(z)
        e = [math.exp(v - m) for v in z]
        return sum(x * w for x, w in zip(payouts, e)) / sum(e)

    lo, hi = -1.0, 1.0
    while mean(lo) > target:
        lo *= 2
    while mean(hi) < target:
        hi *= 2
    for _ in range(200):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if mean(mid) < target else (lo, mid)
    lam = (lo + hi) / 2
    z = [lam * (x - hi_x) / scale for x in payouts]
    m = max(z)
    e = [math.exp(v - m) for v in z]
    s = sum(e)
    return [v / s for v in e]


def publish(mode: str) -> dict:
    with open(os.path.join(LIBRARY, "lookup_tables", f"lookUpTable_{mode}.csv"), encoding="UTF-8") as f:
        lookup = [(int(r[0]), int(r[2])) for r in csv.reader(f)]
    with open(os.path.join(LIBRARY, "lookup_tables", f"lookUpTableSegmented_{mode}.csv"), encoding="UTF-8") as f:
        criteria = {int(r[0]): r[1] for r in csv.reader(f)}
    cats = {c["name"]: c for c in categories(mode)}
    books = {name: [] for name in cats}
    for book, payout in lookup:
        books[criteria[book]].append((book, payout / 100))

    weight = {}
    report = []
    for name, c in cats.items():
        rows = books[name]
        assert len(rows) == c["books"], f"{mode} {name}: {len(rows)} books, expected {c['books']}"
        payouts = [x for _, x in rows]
        sample_mean = sum(payouts) / len(payouts)
        w = tilt(payouts, c["target"])
        for (book, _), wi in zip(rows, w):
            weight[book] = c["prob"] * wi
        ess = 1 / sum(v * v for v in w)  # effective number of books after tilting
        report.append({
            "category": name, "prob": c["prob"], "books": len(rows), "target": c["target"], "sample_mean": sample_mean,
            "shift_pct": (c["target"] / sample_mean - 1) * 100 if sample_mean else 0.0, "effective_books": ess,
        })

    ints = {b: max(1, round(w * TOTAL_WEIGHT)) for b, w in weight.items()}
    path = os.path.join(LIBRARY, "publish_files", f"lookUpTable_{mode}_0.csv")
    with open(path, "w", encoding="UTF-8") as f:
        for book, payout in lookup:
            f.write(f"{book},{ints[book]},{payout}\n")
    return {"mode": mode, "total_weight": sum(ints.values()), "categories": report, "path": path}


def table_rtp(mode: str, cost: float) -> float:
    with open(os.path.join(LIBRARY, "publish_files", f"lookUpTable_{mode}_0.csv"), encoding="UTF-8") as f:
        rows = [(int(r[1]), int(r[2])) for r in csv.reader(f)]
    return sum(w * p for w, p in rows) / sum(w for w, _ in rows) / 100 / cost


def main(modes: list) -> None:
    from categories import TARGETS

    out = {}
    for mode in modes:
        res = publish(mode)
        cost = TARGETS["modes"][mode]["cost"]
        res["rtp"] = table_rtp(mode, cost)
        worst = max(res["categories"], key=lambda r: abs(r["shift_pct"]))
        print(f"{mode}: published RTP {res['rtp'] * 100:.5f}% | largest category shift {worst['category']} "
              f"{worst['shift_pct']:+.2f}% ({worst['books']} books, {worst['effective_books']:.0f} effective)")
        out[mode] = res
    with open(os.path.join(LIBRARY, "weights_report.json"), "w", encoding="UTF-8") as f:
        json.dump(out, f, indent=1)


if __name__ == "__main__":
    from categories import TARGETS

    main(sys.argv[1:] or list(TARGETS["modes"]))
