"""Optimizer targets for thunderborne (math-sdk docs: optimization_section/optimization_algorithm.md, force_info.md).

Every bet mode's buckets add up to its 96% RTP (verify_optimization_input checks the sum). The optimizer assigns books to
buckets IN ORDER, each taking its books out of the pool, so the order below matters:
  1. wincap      books paying MAX_WIN (matched by payout)
  2. freegame    books whose base spin triggered free spins (force record {"symbol": "scatter"})
  3. wildstrike  base-game WILD STRIKE books without a trigger (force record {"wild_strike": "basegame"})
  4. 0           books paying nothing (matched by payout); its hit rate is whatever the others leave
  5. basegame    the remainder: base-game line wins
A buy has wincap, then freegame taking every remaining book.

Targets (user decision, 2026-09-12): the fake math's measured split scaled so each mode sums to 96%, and its max-win
rates. The line-win share is what's left, so the sum is exact. Re-measured for the v3 base layout (2026-09-13): 16M
rounds a mode (two seeds of 8M), each round sorted as the buckets above; the line-win average the targets imply matches
the fake math's own (base 2.21x / 2.23x, WILD BOOST 2.51x / 2.49x, ACTIVATE WHEEL 2.22x / 2.23x, both 2.56x / 2.54x). base, ACTIVATE WHEEL and both were re-measured after their frame
catches were trimmed to bring the fake math to 96% (BASE_STRIKE 0.12, WHEEL_STRIKE 0.14, BOTH_STRIKE 0.38).

Line-win scaling (2026-09-13). The optimizer builds each bucket's distribution over its distinct win amounts, and to hit
the bucket's average it mixes in candidates weighted hard below half the average, so with no scaling it moved base-mode
line wins from 1-5x to under 1x: plain base spins winning 1-4.9x went from 10.7% (natural) to 5.1%, and a base win of 1x
or more from 1 spin in 7.7 to 1 in 12.0. x4 in 1-5x restored the count but piled it into 1-1.9x (38% of line wins
against 21% natural), leaving 2-4.9x at 20% (34% natural); a bias toward 1-5x did nothing. Base-mode split ranges, 20
candidates each (2 optimizer runs x 10): share of line wins at 2-4.9x (natural 33.6%), and distance from the natural
spread (the sum of the band gaps):
  x4 in 1-5x                    20.1% (18.7-24.4), distance 39.2
  x6 in 2-5x                    28.1% (23.9-34.4), distance 28.7
  x1.5 in 1-2x, x4 in 2-5x      23.1% (17.7-41.6), distance 29.1
  x1.5 in 1-2x, x6 in 2-5x      27.5% (22.9-32.4), distance 22.8
  x1.5 in 1-2x, x8 in 2-5x      31.5% (26.4-43.1), distance 17.4  <- LINE_WIN_SCALING, every base-strip mode
Buys are unscaled. Single runs still vary, so run.py then publishes the closest of each mode's 10 candidates
(game_selection.py).
"""

from optimization_program.optimization_config import (
    ConstructScaling,
    ConstructParameters,
    ConstructConditions,
    verify_optimization_input,
)
from game_config import MAX_WIN

# Max win: one round in N.
WINCAP_HIT_RATE = {
    "base": 2_000_000,
    "base_wild_boost": 2_000_000,
    "base_activate_wheel": 1_000_000,
    "base_wild_boost_activate_wheel": 1_000_000,
    "bonus": 9_091,
    "super_bonus": 1_471,
    "wheel_bonus": 4_167,
}

# Base-strip modes: free spins and WILD STRIKE as (RTP share of the mode's 96%, one round in N), and line wins' one in N.
BASE_TARGETS = {
    "base": {"freegame": (0.3103, 199.8), "wildstrike": (0.2271, 88.9), "basegame_hit_rate": 5.27},
    "base_wild_boost": {"freegame": (0.1057, 199.2), "wildstrike": (0.6769, 11.5), "basegame_hit_rate": 4.74},
    "base_activate_wheel": {"freegame": (0.7376, 43.0), "wildstrike": (0.083, 78.0), "basegame_hit_rate": 5.38},
    "base_wild_boost_activate_wheel": {"freegame": (0.5553, 29.2), "wildstrike": (0.3174, 12.4), "basegame_hit_rate": 4.93},
}

# Base-strip modes: line wins of 1-1.99x weighted x1.5 and 2-5x x8 while the optimizer builds the basegame bucket.
LINE_WIN_SCALING = [
    {"criteria": "basegame", "scale_factor": 1.5, "win_range": (1, 1.99), "probability": 1.0},
    {"criteria": "basegame", "scale_factor": 8.0, "win_range": (2, 5), "probability": 1.0},
]

SCATTER_RECORD = {"symbol": "scatter"}
BASE_STRIKE_RECORD = {"wild_strike": "basegame"}


def _conditions(**kwargs):
    return ConstructConditions(**kwargs).return_dict()


def _parameters(test_spins, test_weights):
    return ConstructParameters(
        num_show=5000,
        num_per_fence=10000,
        min_m2m=4,
        max_m2m=8,
        pmb_rtp=1.0,
        sim_trials=5000,
        test_spins=test_spins,
        test_weights=test_weights,
        score_type="rtp",
    ).return_dict()


class OptimizationSetup:
    """Game-specific optimization setup: amends game_config.opt_params."""

    def __init__(self, game_config):
        self.game_config = game_config
        opt_params = {}
        for bet_mode in game_config.bet_modes:
            name, cost, rtp = bet_mode.get_name(), bet_mode.get_cost(), bet_mode.get_rtp()
            wincap_rtp = MAX_WIN / cost / WINCAP_HIT_RATE[name]
            conditions = {"wincap": _conditions(rtp=wincap_rtp, av_win=MAX_WIN, search_conditions=MAX_WIN)}
            if bet_mode.get_buybonus():
                conditions["freegame"] = _conditions(rtp=rtp - wincap_rtp, hr="x")
                parameters = _parameters([10, 20, 50], [0.6, 0.2, 0.2])
                scaling = []
            else:
                targets = BASE_TARGETS[name]
                freegame_rtp, freegame_hr = targets["freegame"]
                strike_rtp, strike_hr = targets["wildstrike"]
                conditions["freegame"] = _conditions(rtp=freegame_rtp, hr=freegame_hr, search_conditions=SCATTER_RECORD)
                conditions["wildstrike"] = _conditions(rtp=strike_rtp, hr=strike_hr, search_conditions=BASE_STRIKE_RECORD)
                conditions["0"] = _conditions(rtp=0, av_win=0, search_conditions=0)
                conditions["basegame"] = _conditions(
                    rtp=rtp - wincap_rtp - freegame_rtp - strike_rtp, hr=targets["basegame_hit_rate"]
                )
                parameters = _parameters([50, 100, 200], [0.3, 0.4, 0.3])
                scaling = LINE_WIN_SCALING
            opt_params[name] = {
                "conditions": conditions,
                "scaling": ConstructScaling(scaling).return_dict(),
                "parameters": parameters,
            }

        self.game_config.opt_params = opt_params
        verify_optimization_input(self.game_config, self.game_config.opt_params)
