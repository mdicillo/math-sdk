"""Publish the optimizer candidate closest to the natural line-win spread, per base-strip mode (user decision, 2026-09-13).

The optimizer writes its 10 best distributions to library/optimization_files/<mode>_0_<N>.csv and publishes the
top-scoring one as publish_files/lookUpTable_<mode>_0.csv. All 10 hit every bucket's RTP and hit rate and their scores
are near-tied, but their line-win shapes vary a lot from run to run. So for each base-strip mode this step publishes the
candidate whose plain line wins (basegame books with no base-game WILD STRIKE) are spread across win sizes closest to
the books' own natural spread: the sum of the gaps between each band's share. Buys keep the optimizer's pick.

Run it after the optimizer and before generate_configs (run.py), which hashes the published tables.
"""

import json
import os

GAME_DIR = os.path.dirname(os.path.abspath(__file__))
LIBRARY = os.path.join(GAME_DIR, "library")
NUM_CANDIDATES = 10

# Line-win bands (x base bet): under 1, 1-2, 2-3, 3-5, 5-10, 10-20, 20+.
BAND_EDGES = [1, 2, 3, 5, 10, 20, float("inf")]
BASE_STRIKE_SEARCH = {"name": "wild_strike", "value": "basegame"}


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
        for index in range(1, NUM_CANDIDATES + 1):
            path = os.path.join(LIBRARY, "optimization_files", f"{mode}_0_{index}.csv")
            table = _read_candidate(path)
            bands = [0] * len(BAND_EDGES)
            for book_id, weight, _win in table:
                if book_id in plain:
                    bands[plain[book_id]] += weight
            share = _shares(bands)
            distance = sum(abs(s - n) for s, n in zip(share, natural))
            rtp = sum(weight * win for _, weight, win in table) / sum(weight for _, weight, _ in table) / costs[mode]
            candidates.append({"candidate": index, "distance": round(distance, 2), "rtp": rtp, "share": share, "table": table})

        best = min(candidates, key=lambda c: c["distance"])
        with open(os.path.join(LIBRARY, "publish_files", f"lookUpTable_{mode}_0.csv"), "w", encoding="UTF-8") as f:
            for book_id, weight, win in best["table"]:
                f.write(f"{book_id},{weight},{int(round(win * 100))}\n")

        print(f"{mode}: published candidate {best['candidate']} (distance {best['distance']}, RTP {best['rtp'] * 100:.4f}%); "
              f"optimizer's pick distance {candidates[0]['distance']}; all: "
              + ", ".join(f"{c['candidate']}:{c['distance']}" for c in candidates))
        selections[mode] = {
            "published_candidate": best["candidate"],
            "distance": best["distance"],
            "natural_share": [round(n, 2) for n in natural],
            "published_share": [round(s, 2) for s in best["share"]],
            "candidate_distances": {c["candidate"]: c["distance"] for c in candidates},
        }

    with open(os.path.join(LIBRARY, "configs", "candidate_selection.json"), "w", encoding="UTF-8") as f:
        json.dump({"band_edges": BAND_EDGES[:-1], "modes": selections}, f, indent=2)
    return selections
