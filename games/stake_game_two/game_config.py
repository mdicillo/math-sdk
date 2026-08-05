"""Stake Game Two — game config (Stake Engine math-SDK port of the TS fake-math model).

Ported from src/config/gameConfig.ts in the stake-game-two repo. See docs/STAKE_PORT.md and
docs/CASCADE_MYSTERY_REWORK.md there for the authoritative math model.

The game is a 5x3, 243-ways CASCADING (tumble) slot with a running win-multiplier ladder, a mystery
"?" wheel, and a three-tier free-spins feature. RTP 96.70%, max win 25,000x.

PORT STATUS — incremental milestones (mirrors how camp_deadwater was ported):
  - Milestone A (built): grid, paytable, reels, wincap, base ways evaluation + the cascade (tumble)
    loop, in base and free spins. Units verified against the TS model (win == paytable*ways*100).
  - Milestone B (built): the +1-per-winning-tumble LADDER (global_multiplier) + WILD's flat 5x pay
    (all-5-reels, once, x ladder, stacks).
  - Milestone C (built): the "?" WHEEL (boost-then-pay ordering; base activates on a win, free always;
    stacked "?"; +5->Upgrade in a 3-scatter round until spent), the three TIERS by scatter count,
    ladder PERSISTENCE (t2/t3 carry; t1 resets until Upgrade), tier-3 OPENING wheel spin, flat +5
    RETRIGGER. Verified: wheel math 0 errors, boost lands on the same drop, t2/t3 ladders carry.
  - Milestone D: the six SDK bet modes (base + 3X Chance, Mystery Chance, Bonus, Super Bonus, Mystery
    Bonus) + per-tier feature reels for the buys + optimizer + full cert run; lock certified MODE_RTP.

Symbols use SDK codes: W = wild, S = scatter, M = mystery "?" (see reels/). H1-H4 / L1-L5 unchanged.

⚠️ Units (see STAKE_PORT.md): ways pays are authored directly as multiples of TOTAL BET — the bet is
   flat in a ways game, so a single-way 3-of-a-kind at pay 0.1 pays exactly 0.10x the stake. The SDK
   multiplies the pay by the ways count. Verify empirically on the first sims run.
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
        self.game_id = "stake_game_two"
        self.provider_number = 0
        self.working_name = "Stake Game Two"
        self.wincap = 25000.0
        self.win_type = "ways"
        self.rtp = 0.967
        self.construct_paths()

        # Game Dimensions — 5x3, 243 ways.
        self.num_reels = 5
        self.num_rows = [3] * self.num_reels

        # Paytable: (match_count, symbol) -> per-way pay as a multiple of TOTAL BET. Mirrors SYMBOLS in
        # gameConfig.ts (the Rage Quit values): H3 == H4, and all five lows share one row.
        # WILD's own pay (flat 5x on all five reels, once) is NOT a per-way pay, so it is not in this
        # table — it is added as a custom pay in Milestone B. Wilds still SUBSTITUTE (handled by the
        # ways evaluator via special_symbols["wild"]).
        self.paytable = {
            (5, "H1"): 3.0, (4, "H1"): 1.5, (3, "H1"): 0.6,
            (5, "H2"): 2.5, (4, "H2"): 1.0, (3, "H2"): 0.5,
            (5, "H3"): 1.5, (4, "H3"): 0.8, (3, "H3"): 0.4,
            (5, "H4"): 1.5, (4, "H4"): 0.8, (3, "H4"): 0.4,
            (5, "L1"): 0.8, (4, "L1"): 0.4, (3, "L1"): 0.1,
            (5, "L2"): 0.8, (4, "L2"): 0.4, (3, "L2"): 0.1,
            (5, "L3"): 0.8, (4, "L3"): 0.4, (3, "L3"): 0.1,
            (5, "L4"): 0.8, (4, "L4"): 0.4, (3, "L4"): 0.1,
            (5, "L5"): 0.8, (4, "L5"): 0.4, (3, "L5"): 0.1,
        }

        self.include_padding = True
        # "multiplier" is intentionally empty — the ladder is applied as a whole-board GLOBAL
        # multiplier (global_multiplier), not a per-wild symbol multiplier.
        self.special_symbols = {"wild": ["W"], "scatter": ["S"], "multiplier": []}
        # WILD's own pay (Milestone B): a flat 5x the TOTAL BET, awarded ONCE when a wild is present on
        # ALL FIVE reels, x the ladder multiplier, and stacked on top of the symbol wins those wilds
        # complete. NOT a per-way pay (so it is not in `paytable`) — see game_executables.add_wild_pay.
        self.wild_pay = 5.0
        # Mystery "?" tile. Lands on the reels (no pays, not special) and must exist on the drawn board;
        # registered explicitly in game_override.create_symbol_map. Inert in Milestone A (the wheel is
        # Milestone C).
        self.mystery_symbol = "M"

        # Scatter count -> free spins (the INITIAL award). Tier is the scatter count: 3/4/5 -> t1/t2/t3
        # -> 10/10/12 spins. Retrigger is a flat +5 regardless of count (Rage Quit rule), encoded on the
        # freegame row as a flat 5 for every count so update_fs_retrigger_amt yields +5.
        self.freespin_triggers = {
            self.basegame_type: {3: 10, 4: 10, 5: 12},
            self.freegame_type: {3: 5, 4: 5, 5: 5},
        }
        self.anticipation_triggers = {
            self.basegame_type: min(self.freespin_triggers[self.basegame_type].keys()) - 1,
            self.freegame_type: min(self.freespin_triggers[self.freegame_type].keys()) - 1,
        }

        # Reels — exported from the TS model (npm run reels:export), WILD->W / BONUS(SCATTER)->S /
        # MYSTERY->M. Base strips carry the symbolDensity position-shaping; feature strips drop it (the
        # provider strips it from the feature pool). Tier 2 has no featureWildWeight override, so it
        # shares FR0. FR_tier1 / FR_tier3 are the per-tier feature pools.
        reels = {
            "BR0": "BR0.csv",
            "FR0": "FR0.csv",
            "FR1": "FR_tier1.csv",
            "FR3": "FR_tier3.csv",
        }
        self.reels = {}
        for r, f in reels.items():
            self.reels[r] = self.read_reels_csv(os.path.join(self.reels_path, f))

        self.padding_reels[self.basegame_type] = self.reels["BR0"]
        self.padding_reels[self.freegame_type] = self.reels["FR0"]

        # --- Mystery "?" wheel (Milestone C) — WHEEL_RESULTS from gameConfig.ts ----------------------
        # Each slot: kind ('add' bumps the ladder by value / 'mult' multiplies it) + relative weight.
        # In a 3-scatter (untilUpgrade) free round the +5 ADD slot becomes 'upgrade' (no boost; flips
        # the ladder persistent) UNTIL an upgrade lands, then it reverts to +5 (Stage 8). See
        # game_executables.roll_wheel.
        self.wheel_results = [
            {"kind": "add", "value": 5, "weight": 40},
            {"kind": "add", "value": 10, "weight": 25},
            {"kind": "add", "value": 20, "weight": 15},
            {"kind": "add", "value": 50, "weight": 8},
            {"kind": "add", "value": 100, "weight": 2},
            {"kind": "mult", "value": 2, "weight": 10},
        ]
        # Base game / Mystery Chance: a "?" activates only on a WINNING drop. Free spins: always.
        self.mystery_activates_on_win = True

        # --- Free-spins tiers (Milestone C), keyed by SCATTER count (3/4/5) --------------------------
        # From BONUS_LEVELS in gameConfig.ts. `spins` (the initial award) lives in freespin_triggers;
        # this carries the rest. increment is 1 for every tier post-rework, applied by update_global_mult.
        #   persistence: 'persistent' (t2/t3, ladder carries the whole feature) or 'untilUpgrade' (t1,
        #     ladder resets each spin until the wheel's Upgrade lands, then persists).
        #   opening_wheel_spins: free wheel rolls at feature entry (t3 = 1).
        #   feature_reel: the per-tier feature strip a BUY draws from (FR1 t1 / FR0 shared t2 / FR3 t3).
        #     Natural triggers use FR0 for now — the per-tier reels are wired to the buys in Milestone D
        #     (a natural 5-scatter is vanishingly rare, so this costs ~nothing; the tier-3 EV that
        #     matters is bought via Mystery Bonus, which WILL draw FR3). Mirrors camp_deadwater.
        self.bonus_tiers = {
            3: {"level": 1, "persistence": "untilUpgrade", "opening_wheel_spins": 0, "feature_reel": "FR1"},
            4: {"level": 2, "persistence": "persistent", "opening_wheel_spins": 0, "feature_reel": "FR0"},
            5: {"level": 3, "persistence": "persistent", "opening_wheel_spins": 1, "feature_reel": "FR3"},
        }
        # Retrigger awards a flat +5 spins for landing >=3 scatters during the feature (Rage Quit rule).
        # Encoded on the freegame trigger row {3:5,4:5,5:5}, so the SDK's update_fs_retrigger_amt yields
        # +5 for any count. Kept here too for readability / future use.
        self.retrigger_spins = 5

        # --- Milestone A bet mode: base only. Distributions mirror the reference cascade games
        # (freegame / zero-win / basegame). The wincap distribution is deliberately OMITTED here: the
        # 25,000x cap is only reachable once the ladder + wheel exist (Milestones B/C), so forcing it now
        # would loop forever in check_repeat. It is added with those mechanics. mult_values is a {1:1}
        # placeholder (the ladder is neutralized in this milestone).
        def base_conditions(base_reel):
            return {
                "freegame": {
                    "reel_weights": {self.basegame_type: {base_reel: 1}, self.freegame_type: {"FR0": 1}},
                    "scatter_triggers": {3: 50, 4: 20, 5: 5},
                    "mult_values": {1: 1},
                    "force_wincap": False,
                    "force_freegame": True,
                },
                "zerowin": {
                    "reel_weights": {self.basegame_type: {base_reel: 1}},
                    "mult_values": {1: 1},
                    "force_wincap": False,
                    "force_freegame": False,
                },
                "basegame": {
                    "reel_weights": {self.basegame_type: {base_reel: 1}},
                    "mult_values": {1: 1},
                    "force_wincap": False,
                    "force_freegame": False,
                },
            }

        def base_like_dists(base_reel):
            c = base_conditions(base_reel)
            return [
                Distribution(criteria="freegame", quota=0.1, conditions=c["freegame"]),
                Distribution(criteria="0", quota=0.4, win_criteria=0.0, conditions=c["zerowin"]),
                Distribution(criteria="basegame", quota=0.5, conditions=c["basegame"]),
            ]

        self.bet_modes = [
            BetMode(
                name="base",
                cost=1.0,
                rtp=self.rtp,
                max_win=self.wincap,
                auto_close_disabled=False,
                is_feature=True,
                is_buybonus=False,
                distributions=base_like_dists("BR0"),
            ),
        ]
