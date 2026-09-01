"""Skull Raiders — Stake Engine math-SDK port of the TS fake-math model.

Ported from src/config/gameConfig.ts in the castle-raid (Skull Raiders) repo. The TS dev model is the
authoritative math spec; see docs/STAKE_PORT.md and docs/WHEEL_FEATURE.md there.

Game: 5x5, 15-payline lines game with multiplier WILDs, a three-tier free-spins bonus, a random
raid-wheel event (ATTACK / STEAL), two per-spin ante boosts, and a mystery bonus buy. Every bet mode
targets 96% RTP; wincap 10,000x. Symbols use SDK codes: W = wild, S = scatter (BONUS); H1-H4 / L1-L5.

PORT STATUS — incremental milestones (mirrors how the reference ports were staged):
  - Milestone A (this commit): grid, 15 paylines, paytable (displayed-x units), symbols, base+feature
    reels, wincap, base LINES evaluation + a stock free-spins loop, and the base/feature multiplier-wild
    bags. Units verified against the TS model (win == paytable*100). Tier logic, the wheel, the full
    bet-mode set and the optimizer land in later milestones (B..F).

Units (see STAKE_PORT.md): line pays are authored directly as multiples of TOTAL BET (the displayed x),
NOT per-line divided. The TS engine's /15 is its own per-line division; the SDK sums line pays x total
bet with no division. Verify empirically on the first sims run: win / (paytable * 100) == 1.0000.
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
        self.game_id = "skull_raiders"
        self.provider_number = 0
        self.working_name = "Skull Raiders"
        self.wincap = 10000.0
        self.win_type = "lines"
        self.rtp = 0.96
        self.construct_paths()

        # Game dimensions — 5x5.
        self.num_reels = 5
        self.num_rows = [5] * self.num_reels

        # Paytable — DISPLAYED x (multiples of total bet). WILD pays on 5 only; it substitutes otherwise.
        # (gameConfig.ts paytable, divided by the 15-payline factor the TS engine re-applies per line.)
        self.paytable = {
            (5, "W"): 45,
            (5, "H1"): 40, (4, "H1"): 14, (3, "H1"): 3,
            (5, "H2"): 16, (4, "H2"): 6.5, (3, "H2"): 1.5,
            (5, "H3"): 11, (4, "H3"): 4.5, (3, "H3"): 1.5,
            (5, "H4"): 7, (4, "H4"): 3, (3, "H4"): 1,
            (5, "L1"): 3, (4, "L1"): 1.5, (3, "L1"): 0.8,
            (5, "L2"): 2.5, (4, "L2"): 1, (3, "L2"): 0.4,
            (5, "L3"): 2.5, (4, "L3"): 1, (3, "L3"): 0.4,
            (5, "L4"): 2.5, (4, "L4"): 1, (3, "L4"): 0.4,
            (5, "L5"): 2, (4, "L5"): 0.8, (3, "L5"): 0.3,
        }

        # 15 fixed paylines (row index per reel, 0 = top). gameConfig.ts:120-136.
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

        # Free-spin awards by scatter count. Base trigger 3/4/5 -> 8/12/15 spins; retrigger adds the
        # landed tier's spin count (capped to bonusMax=30 in a later milestone).
        self.freespin_triggers = {
            self.basegame_type: {3: 8, 4: 12, 5: 15},
            self.freegame_type: {3: 8, 4: 12, 5: 15},
        }
        self.anticipation_triggers = {
            self.basegame_type: min(self.freespin_triggers[self.basegame_type].keys()) - 1,
            self.freegame_type: min(self.freespin_triggers[self.freegame_type].keys()) - 1,
        }

        # Reels — base (BR0), shared feature (FR0), tier-3 feature (FR_tier3, WILD-rich). Exported from
        # the TS reel model (scatterDensity shaping already baked in), WILD->W / BONUS->S.
        reels = {
            "BR0": "BR0.csv",          # base game
            "FR0": "FR0.csv",          # shared feature pool (natural triggers, WILD weight 13.5)
            "FRB": "FR_buy.csv",       # bought tiers 1 & 2 feature pool (WILD weight 14)
            "FR3": "FR_tier3.csv",     # tier 3 / HIDDEN feature pool (WILD weight 22)
        }
        self.reels = {}
        for r, f in reels.items():
            self.reels[r] = self.read_reels_csv(os.path.join(self.reels_path, f))

        self.padding_reels[self.basegame_type] = self.reels["BR0"]
        self.padding_reels[self.freegame_type] = self.reels["FR0"]

        # Three-tier free-spins bonus. count->tier: 3->1, 4->2, 5->3 (spins 8/12/15). Natural triggers
        # clamp to tier 2 (naturalMaxTier); tier 3 (HIDDEN) is only reachable via a Mystery buy. Retrigger
        # adds the landed tier's spins, capped at bonus_max total. gameConfig.ts:144-154,525,512.
        self.natural_max_tier = 2
        self.bonus_max = 30
        # Per-tier feature reel: tier 3 always FR3; bought tiers 1/2 FRB; natural tiers 1/2 FR0.
        self.tier3_reel = "FR3"
        self.buy_reel = "FRB"
        self.natural_reel = "FR0"

        # Multiplier-wild bags (>=1). BASE = tame; FEATURE = fat. Summed within a winning line by the
        # "symbol" multiplier strategy (only >=2 contribute; factor = max(sum, 1)). gameConfig.ts:174-194.
        self.base_mult_bag = {1: 78, 2: 16, 3: 6}
        self.feature_mult_bag = {1: 45, 2: 22, 3: 14, 5: 9, 10: 5, 25: 3, 50: 2}

        mult_values = {self.basegame_type: self.base_mult_bag, self.freegame_type: self.feature_mult_bag}

        # --- Raid wheel (custom base-game event) -------------------------------------------------
        # A wheel round replaces a normal base spin: a plain land board (no scatters, no natural win),
        # then either ATTACK (redraw whole paylines) or STEAL (sweep every 3+ group). Weights mirror
        # gameConfig.ts. Wheel wilds roll from a wheel-only multiplier bag (all >=2, so always contribute).
        self.wheel_attack_share = 0.5  # P(attack); else steal
        # ATTACK: number of paylines redrawn, and per-line the payout symbol + wild count.
        self.attack_line_weights = {1: 60, 2: 28, 3: 9, 4: 2.5, 5: 0.5}
        self.attack_symbol_weights = {"L5": 46, "L4": 30, "L3": 14, "L2": 6, "L1": 2.5, "H4": 1, "H3": 0.4}
        self.attack_extras_weights = {1: 1, 2: 1, 3: 1}  # wilds per redrawn line, uniform [1,3]
        self.attack_mult_bag = {4: 84, 6: 12, 10: 3, 25: 1}
        # STEAL: present symbol + how many cells carry it, and how many multiplier wilds bank.
        self.steal_present_weights = {"L5": 35, "L4": 26, "L3": 18, "L2": 10, "L1": 6, "H4": 3, "H3": 1.5, "H2": 0.4, "H1": 0.15}
        self.steal_present_count_weights = {3: 1, 4: 1, 5: 1}  # present cells, uniform [3,5]
        self.steal_wild_count_weights = {1: 94, 2: 5, 3: 1}
        self.steal_mult_bag = {3: 70, 5: 18, 10: 7, 25: 3, 50: 1.5, 100: 0.5}

        freegame_condition = {
            "reel_weights": {self.basegame_type: {"BR0": 1}, self.freegame_type: {"FR0": 1}},
            "scatter_triggers": {3: 50, 4: 20, 5: 5},
            "mult_values": mult_values,
            "force_wincap": False,
            "force_freegame": True,
        }
        basegame_condition = {
            "reel_weights": {self.basegame_type: {"BR0": 1}},
            "mult_values": mult_values,
            "force_wincap": False,
            "force_freegame": False,
        }
        wincap_condition = {
            "reel_weights": {self.basegame_type: {"BR0": 1}, self.freegame_type: {"FR0": 1, "FR3": 3}},
            "scatter_triggers": {4: 1, 5: 2},
            "mult_values": mult_values,
            "force_wincap": True,
            "force_freegame": True,
        }
        zerowin_condition = {
            "reel_weights": {self.basegame_type: {"BR0": 1}},
            "mult_values": mult_values,
            "force_wincap": False,
            "force_freegame": False,
        }
        # A buy forces the feature every round; the forced scatter count locks the tier. (The freegame
        # feature reel is repointed to the tier's pool at runtime in get_current_distribution_conditions,
        # so the reel_weights[freegame] here is just a placeholder default.) {3,4,5} evenly exercises all
        # three tiers (and the FRB / FR3 pools) in one mode for Milestone C.
        buy_condition = {
            "reel_weights": {self.basegame_type: {"BR0": 1}, self.freegame_type: {"FRB": 1}},
            "scatter_triggers": {3: 1, 4: 1, 5: 1},
            "mult_values": mult_values,
            "force_wincap": False,
            "force_freegame": True,
        }
        # A wheel round: the land draws from BR0, then the wheel builds the win. `force_wheel` is read in
        # run_spin (a custom flag; the framework only knows force_wincap/force_freegame).
        wheel_condition = {
            "reel_weights": {self.basegame_type: {"BR0": 1}},
            "mult_values": mult_values,
            "force_wincap": False,
            "force_freegame": False,
            "force_wheel": True,
        }

        mode_maxwins = {"base": self.wincap, "bonus": self.wincap}
        # NOTE (Milestone A): the `wincap` forced-max-win distribution is intentionally omitted until
        # Milestone F, when a WCAP feature reel + a feature that can actually reach 10,000x exist. Forcing
        # it now would make `check_repeat` resample forever (no round can hit the cap yet).
        self.bet_modes = [
            BetMode(
                name="base",
                cost=1.0,
                rtp=self.rtp,
                max_win=mode_maxwins["base"],
                auto_close_disabled=False,
                is_feature=True,
                is_buybonus=False,
                distributions=[
                    Distribution(criteria="freegame", quota=0.1, conditions=freegame_condition),
                    Distribution(criteria="wheel", quota=0.05, conditions=wheel_condition),
                    Distribution(criteria="0", quota=0.35, win_criteria=0.0, conditions=zerowin_condition),
                    Distribution(criteria="basegame", quota=0.5, conditions=basegame_condition),
                ],
            ),
            BetMode(
                name="bonus",
                cost=100.0,
                rtp=self.rtp,
                max_win=mode_maxwins["bonus"],
                auto_close_disabled=False,
                is_feature=False,
                is_buybonus=True,
                distributions=[
                    Distribution(criteria="freegame", quota=1.0, conditions=buy_condition),
                ],
            ),
        ]
