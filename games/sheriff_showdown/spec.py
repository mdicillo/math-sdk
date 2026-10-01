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
