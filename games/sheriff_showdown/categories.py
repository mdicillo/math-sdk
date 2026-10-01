"""The published categories (targets.json, from targets.py): per bet mode, each category's exact probability, its
target average payout, and how many books it gets.

Weights (user decision 2026-09-30): every category keeps its exact probability; inside a category the books' weights
are tilted only enough to hit its target average. The targets come from the exact model, and each mode's small
remaining gap to 96.00% (the model's own sampling error, after the re-solve) goes into the categories whose averages
carry it (ABSORB), in proportion to their share of the return.

Books per mode: BOOKS (default 100,000; SHERIFF_BOOKS overrides it for debug runs). Each paid Showdown outcome gets
one book (its board and award are fixed by the outcome); the rest are shared by SHARES.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BOOKS = int(os.environ.get("SHERIFF_BOOKS", 100_000))

with open(os.path.join(HERE, "targets.json"), encoding="UTF-8") as f:
    TARGETS = json.load(f)

# Where a mode's remaining gap to 96.00% goes: the categories whose averages are sample estimates for that mode.
ABSORB = {
    "base": ["basegame"],
    "showdown_ante": ["basegame"],
    "wild_ante": ["basegame", "sharpshooter"],
    "sharpshooter_ante": ["sharpshooter"],
    "buy_sheriff": ["buy_sheriff_none"],
    "buy_posse": ["buy_posse_none"],
    "buy_showdown": ["buy_showdown_none"],
}

# Book shares of a paid mode's non-Showdown books, and of a bonus tier's books by big X class.
PAID_SHARES = {"sharpshooter": 0.12, "basegame": 0.50, "sheriff": 0.24, "posse": 0.10, "showdown": 0.04}
CLASS_SHARES = {"none": 0.58, "25": 0.06, "50": 0.06, "100": 0.06, "250": 0.06, "500": 0.06, "1000": 0.06, "5000": 0.06}


def categories(mode: str, rtp: float = 0.96) -> list:
    """A mode's categories with `target` (the average its books are tuned to) and `books` (how many it gets)."""
    m = TARGETS["modes"][mode]
    cats = [dict(c) for c in m["categories"] if c["prob"] > 0]
    for c in cats:
        c["target"] = c["mean"]
    gap = rtp * m["cost"] - sum(c["prob"] * c["mean"] for c in cats)
    absorb = [c for c in cats if c["name"] in ABSORB[mode]]
    total = sum(c["prob"] * c["mean"] for c in absorb)
    for c in absorb:
        c["target"] = c["mean"] + gap * (c["prob"] * c["mean"] / total) / c["prob"]
        c["gap_share"] = gap * (c["prob"] * c["mean"] / total)

    showdowns = [c for c in cats if c["kind"] == "showdown"]
    for c in showdowns:
        c["books"] = 1
    rest = BOOKS - len(showdowns)
    shares = {}
    for c in cats:
        if c["kind"] == "showdown":
            continue
        if c["kind"] == "bonus":
            group = c["bonus"] if c["scatters"] else None
            shares[c["name"]] = (PAID_SHARES[group] if group else 1.0) * CLASS_SHARES[c["x_class"]]
        else:
            shares[c["name"]] = PAID_SHARES[c["name"]]
    norm = sum(shares.values())
    for c in cats:
        if c["kind"] != "showdown":
            c["books"] = int(rest * shares[c["name"]] / norm)
    # Rounding leftovers go to the biggest category.
    biggest = max((c for c in cats if c["kind"] != "showdown"), key=lambda c: c["books"])
    biggest["books"] += BOOKS - sum(c["books"] for c in cats)
    assert sum(c["books"] for c in cats) == BOOKS
    return cats
