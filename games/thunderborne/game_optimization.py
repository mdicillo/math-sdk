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
the fake math's own (base 2.17x / 2.23x, WILD BOOST 2.51x / 2.49x, ACTIVATE WHEEL 2.24x / 2.23x, both 2.54x / 2.54x).

Line-win scaling (2026-09-13). The optimizer builds each bucket's distribution over its distinct win amounts, and to hit
the bucket's average it mixes in candidates weighted hard below half the average, so with no scaling it moved base-mode
line wins from 1-5x to under 1x: plain base spins winning 1-4.9x went from 10.7% (natural) to 5.1%, and a base win of 1x
or more from 1 spin in 7.7 to 1 in 12.0. Base-mode trials on the v3 books (plain base spins 1-4.9x / win of 1x or more):
x2 in 1-5x 7.1% / 1 in 9.9; x4 in 1-5x 12.6% and 11.4% on two runs / 1 in 6.7 and 7.3; x2 in 1-2x with x4.5 in 2-5x
8.8% / 1 in 8.7; bias toward 1-5x 4.4% / 1 in 13.1; x3 in 1-5x with x0.5 under 1x (and x0.6 at 10x+) piled into 1-1.9x.
x4 in 1-5x is used for every base-strip mode (their natural line-win spreads match base's); buys are unscaled.
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
    "base": {"freegame": (0.3029, 199.7), "wildstrike": (0.2428, 82.1), "basegame_hit_rate": 5.28},
    "base_wild_boost": {"freegame": (0.1057, 199.2), "wildstrike": (0.6769, 11.5), "basegame_hit_rate": 4.74},
    "base_activate_wheel": {"freegame": (0.7419, 43.0), "wildstrike": (0.0776, 83.7), "basegame_hit_rate": 5.37},
    "base_wild_boost_activate_wheel": {"freegame": (0.5516, 29.1), "wildstrike": (0.3221, 12.0), "basegame_hit_rate": 4.95},
}

# Base-strip modes: line wins of 1-5x weighted x4 while the optimizer builds the basegame bucket (see the docstring).
LINE_WIN_SCALING = [{"criteria": "basegame", "scale_factor": 4.0, "win_range": (1, 5), "probability": 1.0}]

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
