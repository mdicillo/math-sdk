"""Thunderborne game configuration, inherits from src/config/config.py.

Source of truth: the rebuild's fake math (thunderborne-rebuild src/config/gameConfig.ts, src/rgs/fakeMath/provider.ts).
Reel strips are exported from it exactly (reels/*.csv); symbol ids match the client (T = "10", N = "9").
"""

import os
from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

# Maximum payout for a single round, in multiples of the base bet. The round ends there, even mid-feature.
MAX_WIN = 5000.0

# The most a base-game spin pays (× base bet): WILD STRIKE is never aimed past it. WILD BOOST lifts it to MAX_WIN.
BASE_WIN_CEILING = 2500.0

# Win-level ladders (× base bet), gameConfig.ts WIN_LEVEL_BANDS: each value is a level's upper edge; a win below
# edge N is level N (1-based), at or above the last edge (the wincap) level 11. "standard" scores one spin's win,
# "endFeature" a whole feature total.
WIN_LEVEL_BANDS = {
    "standard": [0.1, 1, 2, 5, 10, 20, 50, 75, 100, MAX_WIN],
    "endFeature": [0.1, 75, 100, 125, 150, 200, 250, 300, 400, MAX_WIN],
}

# Bet mode costs (× base bet). Each ante combination is its own mode.
MODE_COSTS = {
    "base": 1.0,
    "base_wild_boost": 3.0,
    "base_activate_wheel": 3.0,
    "base_wild_boost_activate_wheel": 6.0,
    "bonus": 100.0,
    "super_bonus": 300.0,
    "wheel_bonus": 150.0,
}

# Base-game reel strip for each mode that spins the base game (gameConfig.ts BASE_STRIP / ANTE_STRIPS).
MODE_BASE_REELS = {
    "base": "BR0",
    "base_wild_boost": "BR_WB",
    "base_activate_wheel": "BR_AW",
    "base_wild_boost_activate_wheel": "BR_WBAW",
}

# WILD STRIKE (provider.ts StrikeTuning). A strike size that fills every open cell (neither WILD nor BONUS).
FULL_BOARD = "full"

# How many wilds a strike adds: {(from, to): weight}, a count from..to at random.
STRIKE_SIZES = {
    (1, 1): 30,
    (2, 2): 25,
    (3, 3): 18,
    (4, 4): 11,
    (5, 5): 7,
    (6, 6): 4,
    (7, 9): 0.3,
    (10, 14): 0.1,
    (FULL_BOARD, FULL_BOARD): 0.03,
}

# Each new wild's multiplier: {multiplier: weight}.
STRIKE_MULTIPLIERS = {3: 40, 4: 25, 5: 17, 7: 11, 10: 7}

# frame_on_wild: on a spin where WILDs land, the chance the frame settles on one (then every landed WILD beams).
# chance_by_beams: strike chance with 1, 2, 3+ beaming WILDs. floor / ceiling: a strike's spin pays between them
# (× base bet). aim_tries: random placements tried at a size; aim_lean: the in-range ones are picked with weight
# pay^-aim_lean. resizes: how many times a strike that can't land in range changes its size by one wild.
BASE_STRIKE = {
    "frame_on_wild": 0.355,
    "chance_by_beams": [0.25, 0.5, 0.75],
    "sizes": STRIKE_SIZES,
    "multipliers": STRIKE_MULTIPLIERS,
    "floor": 5,
    "ceiling": BASE_WIN_CEILING,
    "aim_tries": 40,
    "aim_lean": 3.25,
    "resizes": 6,
}

# WILD BOOST (alone or with ACTIVATE WHEEL): the frame catches WILDs more often, each beam is likelier to strike, and
# the base-game ceiling lifts to MAX_WIN.
BOOST_STRIKE = {
    "frame_on_wild": 0.57,
    "chance_by_beams": [0.4, 0.65, 0.9],
    "sizes": STRIKE_SIZES,
    "multipliers": STRIKE_MULTIPLIERS,
    "floor": 5,
    "ceiling": MAX_WIN,
    "aim_tries": 40,
    "aim_lean": 3.25,
    "resizes": 6,
}

# Base-game WILD STRIKE tuning for each mode that spins the base game.
MODE_BASE_STRIKE = {
    "base": BASE_STRIKE,
    "base_wild_boost": BOOST_STRIKE,
    "base_activate_wheel": BASE_STRIKE,
    "base_wild_boost_activate_wheel": BOOST_STRIKE,
}


class GameConfig(Config):
    """Thunderborne: 3 reels × 5 rows, 15 paylines, 3-of-a-kind left to right."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "thunderborne"
        self.game_name = "thunderborne"
        self.provider_number = 0
        self.working_name = "Thunderborne"
        self.wincap = MAX_WIN
        self.win_type = "lines"
        self.rtp = 0.9600
        self.construct_paths()

        # Game Dimensions
        self.num_reels = 3
        self.num_rows = [5] * self.num_reels

        # 3-of-a-kind pays, × base bet per line; lines are summed (no division by the line count).
        self.paytable = {
            (3, "W"): 25,
            (3, "H3"): 15,
            (3, "H2"): 10,
            (3, "H1"): 6,
            (3, "M3"): 4,
            (3, "M2"): 3,
            (3, "M1"): 2,
            (3, "A"): 1.5,
            (3, "K"): 0.7,
            (3, "Q"): 0.7,
            (3, "J"): 0.3,
            (3, "T"): 0.3,
            (3, "N"): 0.3,
        }

        # Row index on reels 0, 1, 2. Keys are 0-based to match the client's lineId (the SDK emits them as lineIndex).
        self.paylines = {
            0: [0, 0, 0],
            1: [1, 1, 1],
            2: [2, 2, 2],
            3: [3, 3, 3],
            4: [4, 4, 4],
            5: [1, 2, 3],
            6: [3, 2, 1],
            7: [1, 0, 1],
            8: [2, 1, 2],
            9: [3, 2, 3],
            10: [4, 3, 4],
            11: [0, 1, 0],
            12: [1, 2, 1],
            13: [2, 3, 2],
            14: [3, 4, 3],
        }

        self.include_padding = True
        self.special_symbols = {"wild": ["W"], "scatter": ["S"], "multiplier": ["W"]}

        self.freespin_triggers = {
            self.basegame_type: {3: 10},
            self.freegame_type: {3: 5},
        }
        self.anticipation_triggers = {
            self.basegame_type: min(self.freespin_triggers[self.basegame_type].keys()) - 1,
            self.freegame_type: min(self.freespin_triggers[self.freegame_type].keys()) - 1,
        }

        # Reels
        reels = {
            "BR0": "BR0.csv",
            "BR_WB": "BR_WB.csv",
            "BR_AW": "BR_AW.csv",
            "BR_WBAW": "BR_WBAW.csv",
            "FR0": "FR0.csv",
        }
        self.reels = {}
        for r, f in reels.items():
            self.reels[r] = self.read_reels_csv(os.path.join(self.reels_path, f))

        self.padding_reels[self.basegame_type] = self.reels["BR0"]
        self.padding_reels[self.freegame_type] = self.reels["FR0"]

        # Steps 1–2 (grid, pays, strips, modes, base-game WILD STRIKE): every base-strip mode is a single "basegame"
        # criteria with its own strip and strike tuning. Free spins come in a later step, with their criteria.
        def base_modes(name):
            return [
                Distribution(
                    criteria="basegame",
                    quota=1.0,
                    conditions={
                        "reel_weights": {
                            self.basegame_type: {MODE_BASE_REELS[name]: 1},
                            self.freegame_type: {"FR0": 1},
                        },
                        "wild_strike": MODE_BASE_STRIKE[name],
                        "force_wincap": False,
                        "force_freegame": False,
                    },
                ),
            ]

        # Buys plant the trigger (force_freegame). Not simulated until the free spins are ported.
        def buy_modes_placeholder():
            return [
                Distribution(
                    criteria="freegame",
                    quota=1.0,
                    conditions={
                        "reel_weights": {
                            self.basegame_type: {"BR0": 1},
                            self.freegame_type: {"FR0": 1},
                        },
                        "force_wincap": False,
                        "force_freegame": True,
                    },
                ),
            ]

        self.bet_modes = []
        for name in MODE_BASE_REELS:
            self.bet_modes.append(
                BetMode(
                    name=name,
                    cost=MODE_COSTS[name],
                    rtp=self.rtp,
                    max_win=self.wincap,
                    auto_close_disabled=False,
                    is_feature=True,
                    is_buybonus=False,
                    distributions=base_modes(name),
                )
            )
        for name in ["bonus", "super_bonus", "wheel_bonus"]:
            self.bet_modes.append(
                BetMode(
                    name=name,
                    cost=MODE_COSTS[name],
                    rtp=self.rtp,
                    max_win=self.wincap,
                    auto_close_disabled=False,
                    is_feature=False,
                    is_buybonus=True,
                    distributions=buy_modes_placeholder(),
                )
            )

    def get_win_level(self, win_amount: float, winlevel_key: str) -> int:
        """Win (× base bet) → level 1..11 on the WIN_LEVEL_BANDS ladder (the client's winLevel)."""
        bands = WIN_LEVEL_BANDS[winlevel_key]
        for idx, edge in enumerate(bands):
            if win_amount < edge:
                return idx + 1
        return len(bands) + 1
