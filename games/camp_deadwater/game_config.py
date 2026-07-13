"""Camp Deadwater — game config (Stake Engine math-SDK port of the TS fake-math model).

Ported from src/config/gameConfig.ts in the camp-deadwater repo. See docs/STAKE_PORT.md there.

PORT STATUS (incremental — see the port checklist):
  - Grid, paytable, paylines, reels, wincap: OURS (this file).
  - Multiplier (merit badge), additive Helping Hands tumble, 3 tiers, antes, tier upgrade:
    NOT yet ported — this pass still inherits 0_0_lines' feature logic. The multiplier is
    NEUTRALIZED ({1:1}) so base-game line math can be verified against our sim first.

⚠️ Paytable values below are our DISPLAYED× multiples (e.g. H1 3-of-a-kind = 3×). To be verified:
   whether the SDK sums per-line paytable values directly as ×total-bet (then these are correct) or
   divides by the payline count (then multiply by 15). Verified empirically via a forced board.
"""

import os
from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode


class GameConfig(Config):

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "camp_deadwater"
        self.provider_number = 0
        self.working_name = "Camp Deadwater"
        self.wincap = 5000.0
        self.win_type = "lines"
        self.rtp = 0.96
        self.construct_paths()

        # Game Dimensions — 5x5 lines game.
        self.num_reels = 5
        self.num_rows = [5] * self.num_reels

        # Paytable: (match_count, symbol) -> DISPLAYED x-multiple (see units caveat in the header).
        self.paytable = {
            (5, "W"): 60,
            (5, "H1"): 55, (4, "H1"): 12, (3, "H1"): 3,
            (5, "H2"): 22, (4, "H2"): 5.5, (3, "H2"): 1.5,
            (5, "H3"): 15, (4, "H3"): 4, (3, "H3"): 1.2,
            (5, "H4"): 10, (4, "H4"): 2.5, (3, "H4"): 0.9,
            (5, "L1"): 3, (4, "L1"): 1.2, (3, "L1"): 0.6,
            (5, "L2"): 3, (4, "L2"): 1.2, (3, "L2"): 0.6,
            (5, "L3"): 2.5, (4, "L3"): 1, (3, "L3"): 0.4,
            (5, "L4"): 2.5, (4, "L4"): 1, (3, "L4"): 0.4,
            (5, "L5"): 2, (4, "L5"): 0.8, (3, "L5"): 0.3,
        }

        # 15 fixed paylines (row index per reel, 0 = top). Mirrors PAYLINES in gameConfig.ts.
        self.paylines = {
            1: [0, 0, 0, 0, 0],
            2: [1, 1, 1, 1, 1],
            3: [2, 2, 2, 2, 2],
            4: [3, 3, 3, 3, 3],
            5: [4, 4, 4, 4, 4],
            6: [0, 1, 2, 3, 4],
            7: [4, 3, 2, 1, 0],
            8: [0, 1, 2, 1, 0],
            9: [4, 3, 2, 3, 4],
            10: [1, 2, 3, 2, 1],
            11: [3, 2, 1, 2, 3],
            12: [0, 1, 0, 1, 0],
            13: [4, 3, 4, 3, 4],
            14: [0, 2, 4, 2, 0],
            15: [4, 2, 0, 2, 4],
        }

        self.include_padding = True
        self.special_symbols = {"wild": ["W"], "scatter": ["S"], "multiplier": ["W"]}

        # Scatter count -> free spins. Base trigger 3/4/5 -> 8/12/15; retrigger awards the same.
        self.freespin_triggers = {
            self.basegame_type: {3: 8, 4: 12, 5: 15},
            self.freegame_type: {3: 8, 4: 12, 5: 15},
        }
        self.anticipation_triggers = {
            self.basegame_type: min(self.freespin_triggers[self.basegame_type].keys()) - 1,
            self.freegame_type: min(self.freespin_triggers[self.freegame_type].keys()) - 1,
        }

        # Reels — exported from the TS model (npm run reels:export), WILD->W / BONUS->S.
        reels = {
            "BR0": "BR0.csv",
            "FR0": "FR0.csv",
            "FR2": "FR_tier2.csv",
            "FR3": "FR_tier3.csv",
            "ANTE2": "BR_ante2.csv",
            "ANTE3": "BR_ante3.csv",
            "WCAP": "FRWCAP.csv",
        }
        self.reels = {}
        for r, f in reels.items():
            self.reels[r] = self.read_reels_csv(os.path.join(self.reels_path, f))

        self.padding_reels[self.basegame_type] = self.reels["BR0"]
        self.padding_reels[self.freegame_type] = self.reels["FR0"]
        # Per-wild multipliers are unused — our merit badge is a single WHOLE-SPIN multiplier applied via
        # the "global" strategy (see game_override / game_executables). Kept as {1:1} (harmless no-op).
        self.padding_symbol_values = {"W": {"multiplier": {1: 1}}}

        # Merit-badge distribution — integer-scaled (×50) from WILD_MULTIPLIERS in gameConfig.ts
        # ({1:50,2:30,3:15,5:5,10:0.06,50:0.02}). The badge is rolled per spin from this and cashes on a
        # wild-in-win (whole spin). Drives both base and free games (the badge is live in both).
        badge_dist = {1: 2500, 2: 1500, 3: 750, 5: 250, 10: 3, 50: 1}
        # A high-weighted variant lets the optimizer force the 5000× tail via the 10×/50× badges.
        badge_dist_hot = {10: 40, 50: 60}

        # --- Helping Hands feature (ported from HANDS_FEATURE / GRAB_REFILL in gameConfig.ts) --------
        # On a triggered free spin the natural board pays first, then zombie hands clear non-wild cells
        # BELOW each reel's lowest wild, the reel tumbles down (wilds preserved), and the top refills
        # from a WILD-RICH pool. The tumbled board's win is ADDED (see gamestate.run_freespin).
        self.hands_trigger_chance = 0.14
        self.hands_min_height = 2
        self.hands_max_height = self.num_rows[0]  # 5
        self.hands_count_weights = {1: 50, 2: 30, 3: 15, 4: 4, 5: 1}  # number of hands (capped by tier/eligible)
        self.hands_height_weights = {2: 30, 3: 18, 4: 9, 5: 3}  # cells cleared (min 2; height-1 dropped)
        self.hands_max_by_tier = {1: 3, 2: 4, 3: 5}
        # Per-tier merit-badge FLOOR in free spins (freeSpinMultiplier): tiers 2/3 light >= 3× / 5×
        # every free spin (badge = max(roll, floor)); tier 1 has no floor. Floors are real badge values.
        self.tier_floor = {1: 1, 2: 3, 3: 5}
        # Wild-rich tumble-refill pool: feature weights with WILD boosted to GRAB_REFILL_WILD_WEIGHT (35)
        # vs the feature 29. BONUS excluded for now (refill-gated retriggers are a later refinement).
        self.grab_dist = {"W": 35, "H1": 6, "H2": 7, "H3": 8, "H4": 9, "L1": 12, "L2": 13, "L3": 14, "L4": 15, "L5": 16}

        # --- Feature tier → spins, and the natural-trigger tier upgrade ("Dig Deeper") -------------
        self.tier_spins = {1: 8, 2: 12, 3: 15}
        self.bonus_max = 30  # cap on total awarded free spins (retriggers)
        # Natural triggers only (base/ante, never buys) can promote the tier: ~95% none, ~4% +1, ~1% +2.
        self.tier_upgrade = {0: 95, 1: 4, 2: 1}

        # --- Simulation distributions (parameterized per reel set) ----------------------------------
        def base_conditions(base_reel):
            """Base-game conditions using `base_reel` for base spins (BR0, or an ANTE reel for antes)."""
            return {
                "wincap": {
                    "reel_weights": {self.basegame_type: {base_reel: 1}, self.freegame_type: {"FR0": 1, "WCAP": 5}},
                    "mult_values": {self.basegame_type: badge_dist, self.freegame_type: badge_dist_hot},
                    "scatter_triggers": {4: 1, 5: 2},
                    "force_wincap": True,
                    "force_freegame": True,
                },
                "freegame": {
                    "reel_weights": {self.basegame_type: {base_reel: 1}, self.freegame_type: {"FR0": 1}},
                    "scatter_triggers": {3: 50, 4: 20, 5: 5},
                    "mult_values": {self.basegame_type: badge_dist, self.freegame_type: badge_dist},
                    "force_wincap": False,
                    "force_freegame": True,
                },
                "zerowin": {
                    "reel_weights": {self.basegame_type: {base_reel: 1}},
                    "mult_values": {self.basegame_type: badge_dist, self.freegame_type: badge_dist},
                    "force_wincap": False,
                    "force_freegame": False,
                },
                "basegame": {
                    "reel_weights": {self.basegame_type: {base_reel: 1}},
                    "mult_values": {self.basegame_type: badge_dist},
                    "force_wincap": False,
                    "force_freegame": False,
                },
            }

        def buy_conditions(free_reel, scatters):
            """Buy-mode conditions: force exactly `scatters` on the trigger board (locks the tier) and run
            the free game on the tier's `free_reel`."""
            return {
                "wincap": {
                    "reel_weights": {self.basegame_type: {"BR0": 1}, self.freegame_type: {free_reel: 1, "WCAP": 5}},
                    "mult_values": {self.basegame_type: badge_dist, self.freegame_type: badge_dist_hot},
                    "scatter_triggers": {scatters: 1},
                    "force_wincap": True,
                    "force_freegame": True,
                },
                "freegame": {
                    "reel_weights": {self.basegame_type: {"BR0": 1}, self.freegame_type: {free_reel: 1}},
                    "scatter_triggers": {scatters: 1},
                    "mult_values": {self.basegame_type: badge_dist, self.freegame_type: badge_dist},
                    "force_wincap": False,
                    "force_freegame": True,
                },
            }

        def base_like_dists(base_reel):
            c = base_conditions(base_reel)
            return [
                Distribution(criteria="wincap", quota=0.001, win_criteria=self.wincap, conditions=c["wincap"]),
                Distribution(criteria="freegame", quota=0.1, conditions=c["freegame"]),
                Distribution(criteria="0", quota=0.4, win_criteria=0.0, conditions=c["zerowin"]),
                Distribution(criteria="basegame", quota=0.5, conditions=c["basegame"]),
            ]

        def buy_dists(free_reel, scatters):
            c = buy_conditions(free_reel, scatters)
            return [
                Distribution(criteria="wincap", quota=0.001, win_criteria=self.wincap, conditions=c["wincap"]),
                Distribution(criteria="freegame", quota=1.0, conditions=c["freegame"]),
            ]

        def mode(name, cost, is_buy, distributions):
            return BetMode(
                name=name, cost=cost, rtp=self.rtp, max_win=self.wincap, auto_close_disabled=False,
                is_feature=(not is_buy), is_buybonus=is_buy, distributions=distributions,
            )

        # Six bet modes: base, two antes (base spins on BONUS-boosted reels), three buys (fixed tiers).
        self.bet_modes = [
            mode("base", 1.0, False, base_like_dists("BR0")),
            mode("ante_searchparty", 2.0, False, base_like_dists("ANTE2")),
            mode("ante_allout", 3.0, False, base_like_dists("ANTE3")),
            mode("bonus_1", 100.0, True, buy_dists("FR0", 3)),
            mode("bonus_2", 250.0, True, buy_dists("FR2", 4)),
            mode("bonus_3", 500.0, True, buy_dists("FR3", 5)),
        ]
