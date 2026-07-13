"""Optimization conditions/parameters for the camp_deadwater bet modes.

Per-criteria RTP targets decompose each mode's 0.96 budget (base ≈0.578 basegame + 0.381 freegame +
0.001 wincap). The optimizer tunes per-sim selection weights to hit these. Buys/antes reuse the base
split; the mode `cost` scales the target payout, so the same rtp split holds. Placeholder targets —
tune against the PAR sheet.
"""

from optimization_program.optimization_config import (
    ConstructScaling,
    ConstructParameters,
    ConstructConditions,
    ConstructFenceBias,
    verify_optimization_input,
)


def _base_like_params(wincap):
    """opt_params entry for a base-style mode (base + antes): basegame/freegame/0/wincap criteria."""
    return {
        "conditions": {
            "wincap": ConstructConditions(rtp=0.001, av_win=wincap, search_conditions=wincap).return_dict(),
            "0": ConstructConditions(rtp=0, av_win=0, search_conditions=0).return_dict(),
            "freegame": ConstructConditions(rtp=0.381, hr=200, search_conditions={"symbol": "scatter"}).return_dict(),
            "basegame": ConstructConditions(hr=3.5, rtp=0.578).return_dict(),
        },
        "scaling": ConstructScaling(
            [
                {"criteria": "basegame", "scale_factor": 1.2, "win_range": (1, 2), "probability": 1.0},
                {"criteria": "basegame", "scale_factor": 1.5, "win_range": (10, 20), "probability": 1.0},
                # Boost the free-game body and SUPPRESS the far tail so etl/cvar stay in the 3-star band
                # (the 5000× cap is still reachable, just rarer).
                {"criteria": "freegame", "scale_factor": 1.3, "win_range": (20, 200), "probability": 1.0},
                {"criteria": "freegame", "scale_factor": 0.6, "win_range": (1000, 2000), "probability": 1.0},
                {"criteria": "freegame", "scale_factor": 0.3, "win_range": (2000, 5000), "probability": 1.0},
            ]
        ).return_dict(),
        "parameters": ConstructParameters(
            num_show=5000, num_per_fence=10000, min_m2m=4, max_m2m=8, pmb_rtp=1.0, sim_trials=5000,
            test_spins=[50, 100, 200], test_weights=[0.3, 0.4, 0.3], score_type="rtp",
        ).return_dict(),
        "distribution_bias": ConstructFenceBias(
            applied_criteria=["basegame"], bias_ranges=[(2.0, 3.0)], bias_weights=[0.5]
        ).return_dict(),
    }


def _buy_params(wincap, cost):
    """opt_params entry for a buy mode: (almost) all RTP in the freegame criteria + the wincap tail.

    Scaling is COST-RELATIVE (win ranges as multiples of `cost`) so each buy concentrates weight around
    its own cost and suppresses its own far tail — this is what keeps cvar/etl in the 3-star band for the
    higher-cost buys (250×/500×), whose wins would otherwise be too top-heavy."""
    return {
        "conditions": {
            "wincap": ConstructConditions(rtp=0.001, av_win=wincap, search_conditions=wincap).return_dict(),
            "freegame": ConstructConditions(rtp=0.959, hr="x").return_dict(),
        },
        "scaling": ConstructScaling(
            [
                {"criteria": "freegame", "scale_factor": 1.5, "win_range": (0.1 * cost, 1.0 * cost), "probability": 1.0},
                {"criteria": "freegame", "scale_factor": 1.3, "win_range": (1.0 * cost, 2.5 * cost), "probability": 1.0},
                {"criteria": "freegame", "scale_factor": 0.5, "win_range": (2.5 * cost, 5.0 * cost), "probability": 1.0},
                {"criteria": "freegame", "scale_factor": 0.25, "win_range": (5.0 * cost, 10.0 * cost), "probability": 1.0},
            ]
        ).return_dict(),
        "parameters": ConstructParameters(
            num_show=5000, num_per_fence=10000, min_m2m=4, max_m2m=8, pmb_rtp=1.0, sim_trials=5000,
            test_spins=[10, 20, 50], test_weights=[0.6, 0.2, 0.2], score_type="rtp",
        ).return_dict(),
        "distribution_bias": ConstructFenceBias(
            applied_criteria=["freegame"], bias_ranges=[(0.5 * cost, 1.5 * cost)], bias_weights=[0.3]
        ).return_dict(),
    }


class OptimizationSetup:
    def __init__(self, game_config):
        self.game_config = game_config
        opt_params = {}
        for bm in game_config.bet_modes:
            name, wincap = bm.get_name(), bm.get_wincap()
            opt_params[name] = _buy_params(wincap, bm.get_cost()) if bm.get_buybonus() else _base_like_params(wincap)

        self.game_config.opt_params = opt_params
        verify_optimization_input(self.game_config, self.game_config.opt_params)
