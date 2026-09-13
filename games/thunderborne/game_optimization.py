"""Optimizer targets for thunderborne (math-sdk docs: optimization_section/optimization_algorithm.md, force_info.md).

Every bet mode's buckets add up to its 96% RTP (verify_optimization_input checks the sum). The optimizer assigns books to
buckets IN ORDER, each taking its books out of the pool, so the order below matters:
  1. wincap      books paying MAX_WIN (matched by payout)
  2. freegame    books whose base spin triggered free spins (force record {"symbol": "scatter"})
  3. wildstrike  base-game WILD STRIKE books without a trigger (force record {"wild_strike": "basegame"})
  4. 0           books paying nothing (matched by payout); its hit rate is whatever the others leave
  5. basegame    the remainder: base-game line wins
A buy has wincap, then freegame taking every remaining book.

Targets (user decision, 2026-09-12): the fake math's measured split (npm run sim) scaled so each mode sums to 96%, and
its max-win rates. The line-win share is what's left, so the sum is exact. No scaling or distribution bias yet: tune
against the PAR sheet after the first run.
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
    "base": {"freegame": (0.2995, 200), "wildstrike": (0.3946, 50), "basegame_hit_rate": 7.4},
    "base_wild_boost": {"freegame": (0.1035, 200), "wildstrike": (0.7382, 10.5), "basegame_hit_rate": 6.7},
    "base_activate_wheel": {"freegame": (0.7395, 43.2), "wildstrike": (0.1307, 50), "basegame_hit_rate": 8.1},
    "base_wild_boost_activate_wheel": {"freegame": (0.5366, 29.2), "wildstrike": (0.3660, 10.3), "basegame_hit_rate": 7.4},
}

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
            opt_params[name] = {
                "conditions": conditions,
                "scaling": ConstructScaling([]).return_dict(),
                "parameters": parameters,
            }

        self.game_config.opt_params = opt_params
        verify_optimization_input(self.game_config, self.game_config.opt_params)
