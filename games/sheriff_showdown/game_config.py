"""Sheriff Showdown game configuration, inherits from src/config/config.py.

Source of truth: the math outline (Dropbox JackslotAudio/SheriffShowdown/math/output/math_spec.md; its JSON copy is
math_spec.json here, loaded by spec.py). Reel strips in reels/ are the outline's strips, copied verbatim.
"""

from src.config.config import Config
from src.config.distributions import Distribution
from src.config.betmode import BetMode

import spec
from categories import categories


class GameConfig(Config):
    """Sheriff Showdown: 5 reels x 5 rows, 10 fixed paylines, left to right."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.game_id = "sheriff_showdown"
        self.game_name = "sheriff_showdown"
        self.provider_number = 0
        self.working_name = "Sheriff Showdown"
        self.wincap = spec.WINCAP_X
        self.win_type = "lines"
        self.rtp = spec.RTP_TARGET
        self.construct_paths()

        # Game Dimensions
        self.num_reels = spec.REELS
        self.num_rows = [spec.ROWS] * self.num_reels

        # Line pays x total bet; the SDK sums line pays with no division by the line count (spec section 4).
        self.paytable = {(n, sym): pay for sym, pays in spec.PAYTABLE.items() for n, pay in pays.items()}

        # Row index per reel (0 = top). Keys are 0-based, matching the events' lineId.
        self.paylines = {idx: list(rows) for idx, rows in enumerate(spec.PAYLINES)}

        # The game's events carry rows 0-4 and the off-screen symbols in `reveal.padding` (spec section 14.5).
        self.include_padding = False
        self.special_symbols = {"wild": [spec.WILD], "scatter": [spec.SCATTER]}

        # Reels: the outline's strip sets (spec.STRIPS, read straight from reels/*.csv).
        self.reels = spec.STRIPS
        self.padding_reels[self.basegame_type] = spec.STRIPS["base"]
        self.padding_reels[self.freegame_type] = spec.STRIPS["fs_sheriff"]

        def distributions(mode: str, strips: str) -> list:
            """One distribution per published category (categories.py): a fixed number of books, each generated
            inside its category (gamestate.run_spin); weights.py sets the published weights."""
            return [
                Distribution(
                    criteria=c["name"],
                    fixed_amt=c["books"],
                    conditions={"reel_weights": {self.basegame_type: {strips: 1}}, "category": c},
                )
                for c in categories(mode)
            ]

        # The paid modes that spin the reels, then the buys (each plays its bought bonus directly).
        self.bet_modes = []
        for name, mode in spec.BASE_MODES.items():
            self.bet_modes.append(
                BetMode(
                    name=name,
                    cost=mode["cost"],
                    rtp=self.rtp,
                    max_win=self.wincap,
                    auto_close_disabled=False,
                    is_feature=True,
                    is_buybonus=False,
                    distributions=distributions(name, mode["strips"]),
                )
            )
        for name, mode in spec.BUY_MODES.items():
            self.bet_modes.append(
                BetMode(
                    name=name,
                    cost=mode["cost"],
                    rtp=self.rtp,
                    max_win=self.wincap,
                    auto_close_disabled=False,
                    is_feature=False,
                    is_buybonus=True,
                    distributions=distributions(name, mode["free_spins"]["strips"]),
                )
            )

        # The published categories, described as the SDK's "fences" (library/configs/math_config.json): the PAR sheet
        # (utils/game_analytics) splits each mode by them. No optimizer runs on this game (weights.py publishes the
        # weights); hr is one round in N, rtp the category's share of the mode's return at its target.
        self.opt_params = {}
        for bm in self.bet_modes:
            conditions = {}
            for c in categories(bm.get_name()):
                conditions[c["name"]] = {
                    "hr": round(1 / c["prob"], 6),
                    "rtp": round(c["prob"] * c["target"] / bm.get_cost(), 10),
                    "av_win": None,
                    "force_search": {"category": c["name"]},
                    "search_range": (-1, -1),
                }
            self.opt_params[bm.get_name()] = {"conditions": conditions, "scaling": []}
