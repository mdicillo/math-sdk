"""Stake Game Two — game config (Stake Engine math-SDK port of the TS fake-math model).

Ported from src/config/gameConfig.ts in the stake-game-two repo. See docs/STAKE_PORT.md and
docs/CASCADE_MYSTERY_REWORK.md there for the authoritative math model.

The game is a 5x3, 243-ways CASCADING (tumble) slot with a running win-multiplier ladder, a mystery
"?" wheel, and a three-tier free-spins feature. RTP 96.70%, max win 25,000x.

PORT STATUS — incremental milestones (mirrors how camp_deadwater was ported):
  - Milestone A (THIS pass): grid, paytable, reels, wincap, base ways evaluation + the cascade
    (tumble) loop, in base and free spins. The MULTIPLIER LADDER is NEUTRALIZED (global_multiplier
    held at 1) and the mystery "?" WHEEL is inert, so base-game ways + tumble math can be verified
    against the TS sim before any of the multiplier mechanics are layered on.
  - Milestone B: the +1-per-winning-tumble ladder + WILD's flat 5x pay (all-5-reels, once).
  - Milestone C: the "?" wheel, the three tiers, persistence, retrigger (+5), tier-3 opening spin.
  - Milestone D: the six bet modes (base, 3X Chance, Mystery Chance, Bonus, Super Bonus, Mystery
    Bonus) + optimizer + full cert run.

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
        # "multiplier" is intentionally empty in Milestone A — the ladder is applied as a whole-board
        # GLOBAL multiplier (global_multiplier), not a per-wild symbol multiplier.
        self.special_symbols = {"wild": ["W"], "scatter": ["S"], "multiplier": []}
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
