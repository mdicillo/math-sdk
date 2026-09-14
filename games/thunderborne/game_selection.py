"""Publish the optimizer candidate closest to the natural line-win spread, per base-strip mode (user decision, 2026-09-13).

The optimizer writes its 10 best distributions to library/optimization_files/<mode>_0_<N>.csv and publishes the
top-scoring one as publish_files/lookUpTable_<mode>_0.csv. All 10 hit every bucket's RTP and hit rate and their scores
are near-tied, but their line-win shapes vary a lot from run to run. So for each base-strip mode this step publishes the
candidate whose plain line wins (basegame books with no base-game WILD STRIKE) are spread across win sizes closest to
the books' own natural spread: the sum of the gaps between each band's share. Buys keep the optimizer's pick.

Before it's scored, every candidate is rebalanced so no single book carries more than MAX_BOOK_SHARE of its weight
(user decision, 2026-09-13). The optimizer weights each distinct payout and splits that weight evenly among the books
paying it, so a payout only one or two books reach can take a large share: at 100,000 books, WILD BOOST's only 1.2x book
came up 1 round in 31. A book over the cap keeps the cap; the excess moves to the nearest payouts below and above it in
the same optimizer bucket that have room, split so the bucket's total weight and average win don't change. Every
bucket's RTP and hit rate stay exactly as optimized. The moves are recorded with the selection.

Run it after the optimizer and before generate_configs (run.py), which hashes the published tables.
"""

import json
import os

from game_config import MAX_WIN

GAME_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.join(GAME_DIR, "library")
NUM_CANDIDATES = 10

# Line-win bands (x base bet): under 1, 1-2, 2-3, 3-5, 5-10, 10-20, 20+.
BAND_EDGES = [1, 2, 3, 5, 10, 20, float("inf")]
BASE_STRIKE_SEARCH = {"name": "wild_strike", "value": "basegame"}
SCATTER_SEARCH = {"name": "symbol", "value": "scatter"}

# No book above this share of a published base-strip table's weight (user decision, 2026-09-13: start at 1%).
MAX_BOOK_SHARE = 0.01
# Payouts tried on each side of a capped payout when looking for room for its excess.
NEIGHBOUR_SEARCH = 25


def _band(win):
    return next(i for i, edge in enumerate(BAND_EDGES) if win < edge)


def _plain_line_wins(mode):
    """Book id -> band, for every basegame book that pays with no base-game WILD STRIKE."""
    struck = set()
    with open(os.path.join(LIBRARY, "forces", f"force_record_{mode}.json"), encoding="UTF-8") as f:
        for record in json.load(f):
            if BASE_STRIKE_SEARCH in record["search"]:
                struck.update(record["bookIds"])
    plain = {}
    with open(os.path.join(LIBRARY, "lookup_tables", f"lookUpTableSegmented_{mode}.csv"), encoding="UTF-8") as f:
        for line in f:
            book_id, criteria, base_win, _free_win = line.strip().split(",")
            book_id = int(book_id)
            if criteria == "basegame" and book_id not in struck and float(base_win) > 0:
                plain[book_id] = _band(float(base_win))
    return plain


def _read_candidate(path):
    """A candidate's distribution: (book id, weight, win x base bet) per book."""
    with open(path, encoding="UTF-8") as f:
        rows = f.read().splitlines()
    start = next(i for i, row in enumerate(rows) if row.startswith("Distribution")) + 1
    table = []
    for row in rows[start:]:
        if row.strip():
            book_id, weight, win = row.split(",")
            table.append((int(book_id), int(weight), float(win)))
    return table


def _shares(values):
    total = sum(values)
    return [value / total * 100 for value in values]


def _buckets(mode, table):
    """Book id -> the optimizer bucket that weights it, assigned in game_optimization.py's order: wincap (paying MAX_WIN),
    freegame (a scatter force record), wildstrike (a base-game strike record), 0 (paying nothing), basegame."""
    triggered, struck = set(), set()
    with open(os.path.join(LIBRARY, "forces", f"force_record_{mode}.json"), encoding="UTF-8") as f:
        for record in json.load(f):
            if SCATTER_SEARCH in record["search"]:
                triggered.update(record["bookIds"])
            if BASE_STRIKE_SEARCH in record["search"]:
                struck.update(record["bookIds"])
    buckets = {}
    for book_id, _weight, win in table:
        if win >= MAX_WIN:
            buckets[book_id] = "wincap"
        elif book_id in triggered:
            buckets[book_id] = "freegame"
        elif book_id in struck:
            buckets[book_id] = "wildstrike"
        elif win == 0:
            buckets[book_id] = "0"
        else:
            buckets[book_id] = "basegame"
    return buckets


def _rebalance(table, buckets):
    """Cap every book at MAX_BOOK_SHARE of the table's weight. A payout whose books are over it keeps the cap per book, and
    the excess moves to the nearest payouts below and above it in the same bucket that have room for it, split in inverse
    proportion to their distance, so the bucket's weight and average win are unchanged. Returns the new table and the
    moves."""
    total = sum(weight for _, weight, _ in table)
    cap = MAX_BOOK_SHARE * total
    books = {}  # (bucket, win) -> book ids
    weights = {}  # (bucket, win) -> the payout's weight
    for book_id, weight, win in table:
        key = (buckets[book_id], win)
        books.setdefault(key, []).append(book_id)
        weights[key] = weights.get(key, 0) + weight

    def per_book(key, extra=0.0):
        return (weights[key] + extra) / len(books[key])

    moves, touched = [], set()
    while True:
        over = [key for key in books if per_book(key) > cap * (1 + 1e-12)]
        if not over:
            break
        key = max(over, key=per_book)
        bucket, win = key
        excess = weights[key] - cap * len(books[key])
        wins = sorted(w for (b, w) in books if b == bucket)
        lows = [w for w in reversed(wins) if w < win][:NEIGHBOUR_SEARCH]
        highs = [w for w in wins if w > win][:NEIGHBOUR_SEARCH]
        for low, high in sorted(((lo, hi) for lo in lows for hi in highs), key=lambda pair: pair[1] - pair[0]):
            to_low = excess * (high - win) / (high - low)
            to_high = excess - to_low
            if per_book((bucket, low), to_low) <= cap and per_book((bucket, high), to_high) <= cap:
                break
        else:
            raise RuntimeError(f"no room near {win}x in the {bucket} bucket for {excess / total:.4%} of the weight")
        moves.append({"bucket": bucket, "win": win, "books": len(books[key]), "book_share_before": round(per_book(key) / total * 100, 3),
                      "moved_share": round(excess / total * 100, 3), "to": [low, high]})
        weights[key] -= excess
        weights[(bucket, low)] += to_low
        weights[(bucket, high)] += to_high
        touched.update([key, (bucket, low), (bucket, high)])

    rebalanced = []
    for book_id, weight, win in table:
        key = (buckets[book_id], win)
        rebalanced.append((book_id, int(round(per_book(key))) if key in touched else weight, win))
    return rebalanced, moves


def publish_closest_candidates(game_config, modes):
    """For each mode, publish the candidate nearest the natural line-win spread; returns {mode: selection record}."""
    costs = {bet_mode.get_name(): bet_mode.get_cost() for bet_mode in game_config.bet_modes}
    selections = {}
    for mode in modes:
        plain = _plain_line_wins(mode)
        natural = [0] * len(BAND_EDGES)
        for band in plain.values():
            natural[band] += 1
        natural = _shares(natural)

        candidates = []
        buckets = None
        for index in range(1, NUM_CANDIDATES + 1):
            path = os.path.join(LIBRARY, "optimization_files", f"{mode}_0_{index}.csv")
            table = _read_candidate(path)
            buckets = buckets or _buckets(mode, table)  # every candidate weights the same books
            table, moves = _rebalance(table, buckets)
            bands = [0] * len(BAND_EDGES)
            for book_id, weight, _win in table:
                if book_id in plain:
                    bands[plain[book_id]] += weight
            share = _shares(bands)
            distance = sum(abs(s - n) for s, n in zip(share, natural))
            total = sum(weight for _, weight, _ in table)
            rtp = sum(weight * win for _, weight, win in table) / total / costs[mode]
            heaviest = max(weight for _, weight, _ in table) / total
            candidates.append({"candidate": index, "distance": round(distance, 2), "rtp": rtp, "share": share, "table": table,
                               "moves": moves, "heaviest": heaviest})

        best = min(candidates, key=lambda c: c["distance"])
        with open(os.path.join(LIBRARY, "publish_files", f"lookUpTable_{mode}_0.csv"), "w", encoding="UTF-8") as f:
            for book_id, weight, win in best["table"]:
                f.write(f"{book_id},{weight},{int(round(win * 100))}\n")

        print(f"{mode}: published candidate {best['candidate']} (distance {best['distance']}, RTP {best['rtp'] * 100:.4f}%, "
              f"heaviest book {best['heaviest'] * 100:.3f}%, {len(best['moves'])} payout(s) rebalanced); "
              f"optimizer's pick distance {candidates[0]['distance']}; all: "
              + ", ".join(f"{c['candidate']}:{c['distance']}" for c in candidates))
        selections[mode] = {
            "published_candidate": best["candidate"],
            "distance": best["distance"],
            "natural_share": [round(n, 2) for n in natural],
            "published_share": [round(s, 2) for s in best["share"]],
            "candidate_distances": {c["candidate"]: c["distance"] for c in candidates},
            "max_book_share": MAX_BOOK_SHARE,
            "heaviest_book_share": round(best["heaviest"] * 100, 4),
            "rebalanced": best["moves"],
        }

    with open(os.path.join(LIBRARY, "configs", "candidate_selection.json"), "w", encoding="UTF-8") as f:
        json.dump({"band_edges": BAND_EDGES[:-1], "modes": selections}, f, indent=2)
    return selections
