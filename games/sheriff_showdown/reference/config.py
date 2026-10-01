"""
Sheriff Showdown - first-pass math configuration.

Every number in here is a design input. The tuner (run_model.py) solves for:
  - paytable scale (then rounds to clean values)
  - base Showdown frequency (fine-tuned to land exactly on target RTP)
  - free-spin Showdown frequency per bonus tier (to return RTP_TARGET x buy price)
  - ante costs (so each ante returns RTP_TARGET of its own cost)

All pays are in multiples of the TOTAL bet (1x = one base bet).
"""

RTP_TARGET = 0.96
MAX_WIN = 50_000          # x bet, applied per round (base spin + any free spins it triggers)
SEED = 20260923

# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------
SYMBOLS = ["H1", "H2", "H3", "M1", "M2", "M3", "M4", "L5", "L4", "L3", "L2", "L1", "W", "S"]
SYMBOL_NAMES = {
    "H1": "Sheriff Star Badge", "H2": "Guns", "H3": "Bullets",
    "M1": "Bottle", "M2": "Rope", "M3": "Gloves", "M4": "Stirrups",
    "L5": "10", "L4": "J", "L3": "Q", "L2": "K", "L1": "A",
    "W": "Wild", "S": "Scatter",
}

# ---------------------------------------------------------------------------
# Paylines: 10 fixed lines on a 5x5 grid. Each entry = row index (0 = top) on reels 1..5.
# 10 lines (not 20): each line carries more of the bet, so a single hit pays a real amount
# (kills the "dribble" of sub-bet wins).
# ---------------------------------------------------------------------------
PAYLINES = [
    [0, 0, 0, 0, 0], [1, 1, 1, 1, 1], [2, 2, 2, 2, 2], [3, 3, 3, 3, 3], [4, 4, 4, 4, 4],
    [0, 1, 2, 1, 0], [4, 3, 2, 3, 4], [1, 2, 3, 2, 1], [3, 2, 1, 2, 3], [0, 1, 0, 1, 0],
]

# Paytable (x total bet, 10 lines): {symbol: (3oak, 4oak, 5oak)}. FIXED - not rescaled.
# Clean values: whole numbers everywhere except the 10's 3-of-a-kind (0.5x), the only pay below
# the bet. 3 of a kind: 10 0.5x, J/Q 1x, A/K and mids 2x, highs 3-5x.
PAYTABLE_FIXED = True
PAYTABLE_DRAFT = {
    "H1": (5, 15, 40),
    "H2": (4, 10, 25),
    "H3": (3, 8, 20),
    "M1": (2, 5, 12),
    "M2": (2, 5, 12),
    "M3": (2, 4, 10),
    "M4": (2, 4, 10),
    "L1": (2, 3, 6),      # A
    "L2": (2, 3, 6),      # K
    "L3": (1, 2, 5),      # Q
    "L4": (1, 2, 5),      # J
    "L5": (0.5, 2, 5),    # 10
}
# Scatter pays anywhere (x total bet), not scaled. 5 = "5 or more".
SCATTER_PAYS = {3: 2.0, 4: 10.0, 5: 50.0}

# ---------------------------------------------------------------------------
# Reel strips: symbol counts per reel [r1, r2, r3, r4, r5], repeated STRIP_REPEAT times
# (longer strips = finer control of scatter odds).
# H1 on reel 3 is reduced (8 copies): it set the old Deputized trigger (H1 in the center cell) and is kept
# as-is (2026-09-28) so the strips are unchanged; the Sharpshooter trigger is now a chance per spin.
# ---------------------------------------------------------------------------
STRIP_REPEAT = 10
# Hand-built strip design: symbols are SPREAD (no symbol repeats within a 5-row window where
# possible). Rarity follows value (lows 8 each, mids 3-4, highs 2), 3 W on reels 2-5:
# ordinary-spin hit rate ~20%, overall ~21%. No stacks.
# A count may be fractional when count x STRIP_REPEAT is a whole number of copies
# (H1 on reel 3 is set in copies).
H1_REEL3_COPIES = 8
REEL_COUNTS_BASE = {
    "H1": [2, 2, H1_REEL3_COPIES / STRIP_REPEAT, 2, 2],
    "H2": [2, 2, 2, 2, 2],
    "H3": [2, 2, 2, 2, 2],
    "M1": [3, 3, 3, 3, 3],
    "M2": [3, 3, 3, 3, 3],
    "M3": [4, 4, 4, 4, 4],
    "M4": [4, 4, 4, 4, 4],
    "L5": [8, 8, 8, 8, 8],
    "L4": [8, 8, 8, 8, 8],
    "L3": [8, 8, 8, 8, 8],
    "L2": [8, 8, 8, 8, 8],
    "L1": [8, 8, 8, 8, 8],
    "W":  [0, 3, 3, 3, 3],
}

# Scatter placement per reel: single scatters spread evenly -> max ONE visible per reel.
# 3 / 4 / 5 scatters ~ 1 in 250 / 6,100 / 375,000 base spins (5 is effectively buy-only).
SCATTERS_PER_REEL = [13, 8, 8, 8, 13]
SCATTER_GROUPS = [[[0]] * n for n in SCATTERS_PER_REEL]

# WILD Ante: swap low symbols for extra wilds (keeps strip length -> scatter odds unchanged).
ANTE_COST = 3.0   # both antes cost 3x per spin; each is tuned to return RTP_TARGET of that
WILD_ANTE_SWAP = {"W": [0, 1.5, 1.5, 1.5, 1.5], "L5": [0, -1, -1, -1, -1], "L4": [0, -0.5, -0.5, -0.5, -0.5]}   # +15 W copies per reel
# WILD Ante: every wild carries a multiplier from the Sharpshooter ladder (plus 1x), heavily weighted
# to 1x-5x but with 10x / 25x / 50x visible (a 25x+ wild shows ~1 in 54 spins). Multipliers add
# per line, as in Sharpshooter. The tuner applies a small tilt (weight x mult^t) so the mode returns
# exactly RTP_TARGET x ANTE_COST; the ladder stays ~90% on 1x-5x.
WILD_ANTE_WILD_MULTS = {1: 45, 3: 30, 5: 15, 7: 4, 9: 2.5, 10: 2, 25: 1, 50: 0.5}

# Free-spin strips: each bonus tier gets its own strips = base counts + a swap (same format
# as WILD_ANTE_SWAP). Chosen by tune_fs_strips.py to hit each tier's "reel_share" target
# (share of bonus value from reel spins). Tier identities:
#   SHERIFF = the Showdown bonus (light), POSSE = the wild bonus (heavy wilds + Sharpshooter),
#   SHOWDOWN = the X bonus (moderate wilds, value stays in X-heavy Showdowns).
FS_STRIP_SEED_OFFSET = 7   # FS strips shuffled with SEED + this (matches tune_fs_strips.py)
# (The "Deputized 1 in N" notes below are the old H1-in-center odds; SHARPSHOOTER_RATE keeps them.)
FS_STRIP_SWAPS = {
    # natural: +1 H1 reel 3 (~11% of value from reels, Deputized 1 in 35)
    "sheriff":  {"H1": [0, 0, 1, 0, 0], "L3": [0, 0, -1, 0, 0]},
    # natural: +6 H1 reel 3 (~29%, Deputized 1 in 9); natural wilds carry the 5x floor
    "posse":    {"H1": [0, 0, 6, 0, 0], "L3": [0, 0, -3, 0, 0], "L2": [0, 0, -3, 0, 0]},
    # natural: +1 H1 reel 3 (~15%, Deputized 1 in 35); value stays in X-heavy Showdowns
    "showdown": {"H1": [0, 0, 1, 0, 0], "L3": [0, 0, -1, 0, 0]},
    # bought: +2 W reels 2-5, +4 H1 reel 3 (~12%, Deputized 1 in 13)
    "buy_sheriff":  {"W": [0, 2, 2, 2, 2], "L5": [0, -1, -1, -1, -1], "L4": [0, -1, -1, -1, -1],
                     "H1": [0, 0, 4, 0, 0], "L3": [0, 0, -2, 0, 0], "L2": [0, 0, -2, 0, 0]},
    # bought: +3 W reels 2-5, +1 H1 reel 3 (~30%, the wild bonus)
    "buy_posse":    {"W": [0, 3, 3, 3, 3], "L5": [0, -2, -2, -2, -2], "L4": [0, -1, -1, -1, -1],
                     "H1": [0, 0, 1, 0, 0], "L3": [0, 0, -1, 0, 0]},
    # bought: +2 H1 reel 3 (~15%, Deputized 1 in 23)
    "buy_showdown": {"H1": [0, 0, 2, 0, 0], "L3": [0, 0, -1, 0, 0], "L2": [0, 0, -1, 0, 0]},
}

# ---------------------------------------------------------------------------
# Sharpshooter feature (2026-09-28; was Deputized, triggered by H1 in the center cell)
# ---------------------------------------------------------------------------
# Triggers at RANDOM on a normal reel spin, with a chance per context (below). The trigger is drawn first;
# a Sharpshooter spin then draws every reel from its scatter-free stops, so it never shows a scatter.
# Every cell can take a wild (no symbol is reserved).
# Chance per normal reel spin: today's odds, kept from the old H1-in-center trigger (reel 3 H1 copies / 626);
# the SHARPSHOOTER Ante's chance is its own (below).
SHARPSHOOTER_RATE = {
    "base": 8 / 626, "wild_ante": 8 / 626,
    "sheriff": 18 / 626, "posse": 68 / 626, "showdown": 18 / 626,
    "buy_sheriff": 48 / 626, "buy_posse": 18 / 626, "buy_showdown": 28 / 626,
    "sharpshooter_ante": 1 / 5,   # SHARPSHOOTER Ante (Mike, 2026-09-29), not an old Deputized odds
}
# The first wild always completes a paying line (guaranteed win); the count below is the total
# (the fallback that converts the reel 1 + reel 2 cells of a line places 2 even when 1 is drawn).
# The wild-count weights are SOLVED (run_model.py): SHARPSHOOTER_WILD_COUNT_DESIGN tilted by
# weight x exp(t x (k - 1)) so the base-game award per Sharpshooter averages SHARPSHOOTER_TARGET_AVG_AWARD
# (the old Deputized average, so the feature keeps its share of base RTP).
SHARPSHOOTER_WILD_COUNT_DESIGN = {1: 85, 2: 12, 3: 2.5, 4: 0.5}   # the old Deputized weights
SHARPSHOOTER_TARGET_AVG_AWARD = 11.6303
SHARPSHOOTER_WILD_COUNT = dict(SHARPSHOOTER_WILD_COUNT_DESIGN)    # replaced by the solved weights
SHARPSHOOTER_MULTS = {3: 78, 5: 14, 7: 4, 9: 2, 10: 1.5, 25: 0.4, 50: 0.1}  # weights
# Multipliers apply per line; multiple multiplier wilds on a line ADD together.
# Presentation (outcome-first): the procedure above decides the AWARD. The wilds shown are then
# rebuilt to display exactly that award with as many wilds as possible (engine.sharpshooter_presentation):
# every shown wild sits inside a winning run, carries a multiplier from SHARPSHOOTER_MULTS (>= the wild floor,
# so >= 3x), and the board's line total equals the award. Kept only when it shows more wilds.
SHARPSHOOTER_PRESENT_MAX_WILDS = 5
SHARPSHOOTER_PRESENT_PAIR_SAMPLE = 150   # single-line wild sets sampled for two-line unions

# SHARPSHOOTER Ante (player-facing: SHARPSHOOTER BOOST; 2026-09-29, Mike): its own bet mode on the base strips,
# Showdown at the base rate (the SHOWDOWN Ante is the Showdown mode). The price is the studio's (it carries a
# convenience premium); the mode's own Sharpshooter content is solved to return RTP_TARGET x the price.
#   - Sharpshooter chance per normal reel spin: SHARPSHOOTER_RATE["sharpshooter_ante"] (1 in 5, Mike).
#   - Wild count 1-6, equal weights (the count shown varies from spin to spin).
#   - Placement: the guaranteed wild as in the base game, then every further wild lands inside a winning run
#     (engine.place_in_run), so every shown wild's multiplier counts. No presentation rebuild: the award
#     procedure's board is the board shown.
#   - Multipliers: the Sharpshooter ladder plus 75x and 100x, tilted weight x multiplier^t; t is SOLVED
#     (run_model.py) so the mode returns RTP_TARGET x SHARPSHOOTER_ANTE_COST.
SHARPSHOOTER_ANTE_COST = 60.0
SHARPSHOOTER_ANTE_WILD_COUNT = {1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1}
SHARPSHOOTER_ANTE_MULTS_DESIGN = {**SHARPSHOOTER_MULTS, 75: 0.05, 100: 0.02}
SHARPSHOOTER_ANTE_TILT_START = 1.4643      # the solver's starting point (last solved value)
SHARPSHOOTER_ANTE_SOLVE_SPINS = 2_000_000  # forced Sharpshooter spins per solve sample (run in parallel)
SHARPSHOOTER_ANTE_SOLVE_ROUNDS = 4          # samples; those drawn near the solved t are pooled for the solve

# ---------------------------------------------------------------------------
# Showdown feature
# ---------------------------------------------------------------------------
SHERIFF_VALUE = 10
CHARACTERS = {  # name: (value, weight); lowest challenger pays 6x
    # 2026-09-26 rework: characters are the middle of the ladder (+ < VS < X). Values raised from
    # 3/4/5/6/7/8/9; weights unchanged so the cast shows up as often as before.
    "Bandit": (6, 30), "Robber": (8, 25), "Cowboy": (10, 18), "Outlaw": (12, 12),
    "Rancher": (15, 8), "Baron": (20, 5), "Villain": (30, 2),
}
SHERIFF_WIN_CHANCE = 0.75   # VS: Sheriff wins -> 10 + challenger (bounty); else challenger value
# 3-9 are the + numbers (the challengers' old values); 10-5000 are the X numbers. 250 fills the
# 1,000x-5,000x X gap.
NUMBERS = [3, 4, 5, 6, 7, 8, 9, 10, 25, 50, 100, 250, 500, 1000, 5000]

# Number weight tables (one weight per NUMBERS entry):
#   "base"  = base game, antes, SHERIFF BONUS
#   "posse" = POSSE BONUS
#   "top"   = SHOWDOWN BONUS
# 2026-09-26 rework: + is the small outcome (10 + 3..9 = 13-19x, the challengers' old values and
# weights, same in every table); X keeps its numbers and tables and stays the big / max-win outcome.
_PLUS = [30, 25, 18, 12, 8, 5, 2, 0, 0, 0, 0, 0, 0, 0, 0]
PLUS_WEIGHTS = {"base": list(_PLUS), "posse": list(_PLUS), "top": list(_PLUS)}
X_WEIGHTS = {
    "base":  [0] * 7 + [700, 200, 70, 25, 4, 2, 0.8, 0.02],   # X5000 weight is SOLVED (MAX_WIN_ODDS_TARGET)
    "posse": [0] * 7 + [800, 115, 30, 60, 34, 13, 2.5, 0.3],  # X100 bumped: fills the 5-10x-price band
    "top":   [0] * 7 + [600, 240, 90, 45, 8, 8, 3, 0.3],
}
# Base game modifier odds (VS, +, X). Bonus tiers: + share fixed, X share SOLVED by the
# tuner so each bonus returns RTP x price, VS takes the remainder.
BASE_MODIFIER_WEIGHTS = (0.70, 0.275, 0.025)   # fixed; the base Showdown RATE is solved instead (was 0.81/0.16/0.03)

# Max-win frequency target (Stake approval: at least 1 in 10,000,000 base spins).
# The tuner sets the base X5000 weight so the base-game Showdown ALONE hits max win this
# often; bonuses triggered from the base game add to it (see report for the total).
MAX_WIN_ODDS_TARGET = 8_000_000

# Base Showdown frequency (per spin) is SOLVED: ordinary spins, Sharpshooter (SHARPSHOOTER_RATE) and
# bonuses (SCATTERS_PER_REEL) are set first, Showdown takes the rest of the RTP budget.
# Feature budget: each feature keeps its share of the previous model's feature RTP, scaled down
# to make room for the ordinary spins. BASE_SHOWDOWN_RATE is only the solver's starting point.
SOLVE_BASE_SHOWDOWN_RATE = True
BASE_SHOWDOWN_RATE = 1 / 77
# SHOWDOWN Ante: Showdown frequency is SOLVED so the mode returns RTP_TARGET x ANTE_COST.

# ---------------------------------------------------------------------------
# Free spins
# ---------------------------------------------------------------------------
# Natural and bought bonuses are SEPARATE modes with their own content.
#   mode "natural": triggered by scatters in the base game / antes. Its average award (target_ev) is
#                   sized to the base-game budget: share of base RTP = trigger rate x target_ev.
#   mode "buy":     its own bet mode. Returns RTP_TARGET x buy_price (the price carries the
#                   convenience charge; set by the studio). Never triggered naturally.
# Per tier: Showdown rate and + share are design inputs; the X share is SOLVED so the round hits its
# target. Guarantees are met by redrawing the round (guaranteed events land on random spins).
FREE_SPIN_TIERS = {
    # ---- natural (triggered in the base game) ----
    "sheriff":  {"label": "SHERIFF BONUS", "mode": "natural", "scatters": 3, "spins": 10, "wild_floor": 0,
                 "guarantees": ["showdown"], "min_showdowns": 1, "target_ev": 52, "reel_share": 0.12,
                 "showdown_rate": 1 / 6, "plus_share": 0.15, "tables": "base"},   # + share was 0.08
    "posse":    {"label": "POSSE BONUS", "mode": "natural", "scatters": 4, "spins": 15, "wild_floor": 5,
                 "guarantees": ["showdown", "sharpshooter"], "target_ev": 192, "reel_share": 0.30,
                 "showdown_rate": 1 / 4, "plus_share": 0.20, "tables": "posse"},
    "showdown": {"label": "SHOWDOWN BONUS", "mode": "natural", "scatters": 5, "spins": 20, "wild_floor": 10,
                 "guarantees": ["showdown"], "target_ev": 432, "reel_share": 0.15,
                 "showdown_rate": 1 / 3.5, "plus_share": 0.30, "tables": "top"},
    # ---- bought (own bet modes) ----
    "buy_sheriff":  {"label": "SHERIFF BONUS (buy)", "mode": "buy", "scatters": 3, "spins": 10, "wild_floor": 0,
                     "guarantees": ["showdown"], "min_showdowns": 2, "buy_price": 100, "reel_share": 0.12,
                     "showdown_rate": 1 / 6, "plus_share": 0.25, "tables": "base"},
    "buy_posse":    {"label": "POSSE BONUS (buy)", "mode": "buy", "scatters": 4, "spins": 15, "wild_floor": 5,
                     "guarantees": ["showdown", "sharpshooter"], "buy_price": 300, "reel_share": 0.30,
                     "showdown_rate": 1 / 4, "plus_share": 0.20, "tables": "posse"},
    "buy_showdown": {"label": "SHOWDOWN BONUS (buy)", "mode": "buy", "scatters": 5, "spins": 20, "wild_floor": 10,
                     "guarantees": ["showdown"], "buy_price": 500, "reel_share": 0.15,
                     "showdown_rate": 1 / 3.5, "plus_share": 0.30, "tables": "top"},
}
RETRIGGER_SPINS = {3: 5, 4: 10, 5: 15}   # scatters during FS -> extra spins (5 = 5+)
RETRIGGER_SPIN_CAP = None                # None = uncapped (minor open issue; model reports how long rounds get)

# ---------------------------------------------------------------------------
# Anticipation (presentation; the math owns every result)
# ---------------------------------------------------------------------------
# Two levels, evaluated per reel on the final board (engine.anticipation_levels); every reel after
# the 2nd scatter anticipates:
#   heavy: ANTICIPATION_HEAVY_SCATTERS+ scatters on the reels to the left (chasing POSSE / SHOWDOWN)
#   light: ANTICIPATION_MIN_SCATTERS+ scatters on the reels to the left (and not heavy)
# While a flagged reel spins, the front end shows that reel's anticipation strip for the level
# (the reel's own symbols with a scatter every N positions), then lands on the math's board.
# Off-screen rows (one above / one below the window) come from the real strip: honest near-misses.
ANTICIPATION_MIN_SCATTERS = 2
ANTICIPATION_HEAVY_SCATTERS = 3
ANTICIPATION_LIGHT_SPACING = 8
ANTICIPATION_HEAVY_SPACING = 5

# ---------------------------------------------------------------------------
# Simulation sizes
# ---------------------------------------------------------------------------
REEL_MC_SPINS = 4_000_000        # per strip set / floor, for reel-spin statistics
VALIDATION_BASE_SPINS = 10_000_000
VALIDATION_BUY_ROUNDS = 200_000
BATCH = 250_000
