"""Sheriff Showdown math data, loaded from the math outline's own output files (copied verbatim): `math_spec.json`
for every weight, table and rule value, and `reels/*.csv` for the exact reel strips. Nothing here is transcribed by
hand; when the outline is regenerated, re-copy the files (the game repo keeps the same copies in
src/rgs/sheriff/data/).

Source of truth: the outline's math_spec.md (implementation spec) and engine.py (reference implementation).
The game client's src/rgs/sheriff/spec.ts + engine.ts is the TypeScript port these rules must match.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(HERE, "math_spec.json"), encoding="UTF-8") as f:
    SPEC = json.load(f)

REELS = SPEC["grid"]["reels"]
ROWS = SPEC["grid"]["rows"]

WILD = "W"
SCATTER = "S"

RTP_TARGET = SPEC["rtp_target"]
# Max win per round, x base bet.
WINCAP_X = float(SPEC["max_win_x_bet"])

# 10 fixed paylines, row index per reel (0 = top).
PAYLINES = SPEC["paylines"]["rows_top_is_0"]

# Line pays x total bet: {symbol: {count: pay}}, in the spec's paytable order (the order ties are broken in).
PAYTABLE = {sym: {int(n): pay for n, pay in pays.items()} for sym, pays in SPEC["paytable_x_total_bet"].items()}
PAYING_SYMBOLS = list(PAYTABLE)

# Scatter pay x total bet by count (the top count pays for that many or more).
SCATTER_PAYS = {int(n): pay for n, pay in SPEC["scatter_pays_x_total_bet"].items()}

# Anticipation (section 13): every reel after the 2nd scatter anticipates; heavy after the 3rd.
ANTICIPATION_MIN_SCATTERS = 2
ANTICIPATION_HEAVY_SCATTERS = 3


def read_strip_csv(path: str) -> list:
    """A strip CSV (`position,reel1..reelN`; position 1 = top of the strip) as one symbol list per reel. Reels have
    different lengths, so shorter columns end in empty cells (the SDK's read_reels_csv expects equal columns)."""
    with open(path, encoding="UTF-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    header = lines[0].split(",")
    reels = [[] for _ in range(len(header) - 1)]
    for line in lines[1:]:
        cells = line.split(",")
        for reel in range(len(reels)):
            sym = cells[reel + 1].strip() if reel + 1 < len(cells) else ""
            if sym:
                reels[reel].append(sym)
    return reels


STRIP_SET_IDS = list(SPEC["reel_strips"]["sets"])
STRIPS = {sid: read_strip_csv(os.path.join(HERE, "reels", SPEC["reel_strips"]["sets"][sid])) for sid in STRIP_SET_IDS}

for _sid, _strips in STRIPS.items():
    assert [len(s) for s in _strips] == SPEC["reel_strips"]["lengths"][_sid], f"strip lengths differ: {_sid}"


def clean_stops(strips: list) -> list:
    """Per reel, the stops whose 5-row window shows no scatter (a Sharpshooter spin draws from these)."""
    out = []
    for strip in strips:
        length = len(strip)
        out.append([stop for stop in range(length) if all(strip[(stop + row) % length] != SCATTER for row in range(ROWS))])
    return out


CLEAN_STOPS = {sid: clean_stops(strips) for sid, strips in STRIPS.items()}

# Bet modes (spec section 14.3): name -> cost x base bet and the strip set its paid spins use.
BASE_MODES = {
    "base": {"cost": 1.0, "strips": "base"},
    "wild_ante": {"cost": SPEC["antes"]["cost_x_bet"], "strips": SPEC["antes"]["wild"]["strips"]},
    "showdown_ante": {"cost": SPEC["antes"]["cost_x_bet"], "strips": SPEC["antes"]["showdown"]["strips"]},
    "sharpshooter_ante": {
        "cost": SPEC["antes"]["sharpshooter"]["cost_x_bet"],
        "strips": SPEC["antes"]["sharpshooter"]["strips"],
    },
}


def num_table(obj: dict) -> dict:
    """A JSON weight table {"3": w, ...} as {3: w, ...}."""
    return {int(k): w for k, w in obj.items()}


# Sharpshooter (section 6): the chance per normal reel spin by strip set, and the shared content.
SHARPSHOOTER_RATE = SPEC["sharpshooter"]["rate_per_spin"]
SHARPSHOOTER_WILD_COUNT = num_table(SPEC["sharpshooter"]["wild_count_weights"])
SHARPSHOOTER_MULTIPLIERS = num_table(SPEC["sharpshooter"]["multiplier_weights"])
# Presentation (section 6 step 6): most wilds shown, and the two-line union sample size.
SHARPSHOOTER_PRESENT_MAX_WILDS = SPEC["sharpshooter"]["presentation"]["max_wilds"]
SHARPSHOOTER_PRESENT_PAIR_SAMPLE = SPEC["sharpshooter"]["presentation"]["pair_sample"]

_SHARP_ANTE = SPEC["antes"]["sharpshooter"]

# Per reel-spin mode: the natural-wild multiplier ladder (WILD Ante) and the mode's own Sharpshooter content
# (SHARPSHOOTER Ante: its chance, wild counts, multipliers, and in-run placement with no step 6 rebuild).
BASE_MODES["wild_ante"]["wild_multipliers"] = num_table(SPEC["antes"]["wild"]["natural_wild_multiplier_weights"])
BASE_MODES["sharpshooter_ante"]["sharpshooter"] = {
    "rate": _SHARP_ANTE["sharpshooter_rate"],
    "wild_count": num_table(_SHARP_ANTE["wild_count_weights"]),
    "multipliers": num_table(_SHARP_ANTE["multiplier_weights"]),
    "in_run": _SHARP_ANTE["placement"] == "in_run",
}
for _strip_id in STRIP_SET_IDS:
    assert 0 <= SHARPSHOOTER_RATE[_strip_id] < 1, f"no Sharpshooter chance for {_strip_id}"

# Showdown (section 8).
SHERIFF_VALUE = SPEC["showdown"]["sheriff_value"]
SHERIFF_WIN_CHANCE = SPEC["showdown"]["sheriff_win_chance_vs"]
# Challengers: board id (the name upper-cased, e.g. BANDIT) -> value, and their draw weights.
CHALLENGERS = {name.upper(): c["value"] for name, c in SPEC["showdown"]["characters"].items()}
CHALLENGER_WEIGHTS = {name.upper(): c["weight"] for name, c in SPEC["showdown"]["characters"].items()}
# Number tables {table: {"PLUS": {number: weight}, "X": {...}}}, without zero-weight entries (+ draws 3-9, X 10-5000).
NUMBER_TABLES = {
    tid: {
        mod: {int(n): v["weight"] for n, v in table[key].items() if v["weight"] > 0}
        for mod, key in (("PLUS", "plus"), ("X", "x"))
    }
    for tid, table in SPEC["showdown"]["number_tables"].items()
}


def showdown_context(rate: float, odds_key: str) -> dict:
    """Everything a Showdown draw needs for one context: its chance per spin, VS / PLUS / X odds and number table."""
    probs = SPEC["showdown"]["modifier_probs_VS_plus_X"][odds_key]
    return {
        "rate": rate,
        "modifiers": dict(zip(("VS", "PLUS", "X"), probs)),
        "table": SPEC["showdown"]["number_table_used"][odds_key],
    }


# The base game and every ante share the base modifier odds and number table; each has its own chance per spin.
BASE_MODES["base"]["showdown"] = showdown_context(SPEC["showdown"]["rate_per_spin"]["base"], "base")
BASE_MODES["wild_ante"]["showdown"] = showdown_context(SPEC["antes"]["wild"]["showdown_rate"], "base")
BASE_MODES["showdown_ante"]["showdown"] = showdown_context(SPEC["antes"]["showdown"]["showdown_rate"], "base")
BASE_MODES["sharpshooter_ante"]["showdown"] = showdown_context(_SHARP_ANTE["showdown_rate"], "base")

# Free spins (section 10). Natural and bought bonuses are separate modes with their own content.
LEVEL_BY_MODE = {"sheriff": 1, "posse": 2, "showdown": 3, "buy_sheriff": 1, "buy_posse": 2, "buy_showdown": 3}
FREE_SPINS_MODES = {
    fid: {
        "id": fid,
        "label": t["label"],
        "level": LEVEL_BY_MODE[fid],
        "source": "buy" if t["mode"] == "buy" else "natural",
        "spins": t["spins"],
        "wild_floor": t["wild_floor"],
        "strips": t["strips"],
        "showdown": {
            "rate": t["showdown_rate"],
            "modifiers": dict(zip(("VS", "PLUS", "X"), t["modifier_probs_VS_plus_X"])),
            "table": t["number_table"],
        },
        # The round is redrawn until it has at least this many Showdowns (and, when needed, a Sharpshooter spin).
        "min_showdowns": t["min_showdowns"],
        "needs_sharpshooter": "sharpshooter" in t["guarantees"],
        "buy_price": t["buy_price_x_bet"],
        "target_return": t["target_return_x_bet"],
    }
    for fid, t in SPEC["free_spins"].items()
}
# Extra spins on a free-spin retrigger by scatter count (the top count = that many or more); the cap (None: uncapped).
RETRIGGER_SPINS = {int(k): v for k, v in SPEC["retrigger_extra_spins"].items()}
RETRIGGER_CAP = SPEC["retrigger_cap"]


def natural_mode_for(scatters: int):
    """Natural free-spins mode by scatter count on a base / ante reel spin (3 / 4 / 5+), or None."""
    if scatters >= 5:
        return FREE_SPINS_MODES["showdown"]
    if scatters == 4:
        return FREE_SPINS_MODES["posse"]
    if scatters == 3:
        return FREE_SPINS_MODES["sheriff"]
    return None

# Buy modes (spec section 14.3): each plays its bought free-spins mode directly (no trigger spin, no scatter pay),
# priced at the mode's buy price.
BUY_MODES = {fid: {"cost": float(m["buy_price"]), "free_spins": m} for fid, m in FREE_SPINS_MODES.items() if m["source"] == "buy"}
