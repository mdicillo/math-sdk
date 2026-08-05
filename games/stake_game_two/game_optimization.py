"""Optimization conditions/parameters for the stake_game_two bet modes.

The optimizer tunes per-simulation selection weights so each mode hits its RTP target from unweighted
noise. Each mode's 0.967 budget is decomposed per criteria:
  - base-style modes (base + the two boosts): wincap + zero + freegame + basegame.
  - buys: (almost) all RTP in the freegame criteria + the wincap tail.

The base/feature SPLIT differs by mode (a forced-"?" mode is base-heavy; a richer-scatter mode is
feature-heavy), so the split targets are per group and expected to be retuned against the PAR sheet —
these are a first, reasonable decomposition, not a settled tune. A stake-priced mode (Mystery Chance)
optimizes in the same 0.967 RTP space: its payouts are x50 but cost is 50, so RTP is unchanged and the
same targets apply. The scaling below suppresses the far tail so cvar/etl stay in the 3-star band.
"""

from optimization_program.optimization_config import (
    ConstructScaling,
    ConstructParameters,
    ConstructConditions,
    ConstructFenceBias,
    verify_optimization_input,
)


def _base_like_params(wincap, basegame_rtp=0.466, freegame_rtp=0.5):
    return {
        "conditions": {
            "wincap": ConstructConditions(rtp=0.001, av_win=wincap, search_conditions=wincap).return_dict(),
            "0": ConstructConditions(rtp=0, av_win=0, search_conditions=0).return_dict(),
            "freegame": ConstructConditions(rtp=freegame_rtp, hr=250, search_conditions={"symbol": "scatter"}).return_dict(),
            "basegame": ConstructConditions(hr=3.0, rtp=basegame_rtp).return_dict(),
        },
        "scaling": ConstructScaling(
            [
                {"criteria": "basegame", "scale_factor": 1.2, "win_range": (1, 5), "probability": 1.0},
                {"criteria": "freegame", "scale_factor": 1.3, "win_range": (20, 200), "probability": 1.0},
                # Suppress the far tail so etl/cvar stay in the 3-star band (the cap is still reachable).
                {"criteria": "freegame", "scale_factor": 0.5, "win_range": (2000, 10000), "probability": 1.0},
                {"criteria": "freegame", "scale_factor": 0.25, "win_range": (10000, 25000), "probability": 1.0},
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
    """Buy mode: almost all RTP in the freegame criteria + the wincap tail. Scaling is COST-RELATIVE so
    each buy concentrates weight around its own cost and suppresses its own far tail — what keeps
    cvar/etl in the 3-star band for the higher-cost buys."""
    return {
        "conditions": {
            "wincap": ConstructConditions(rtp=0.001, av_win=wincap, search_conditions=wincap).return_dict(),
            "freegame": ConstructConditions(rtp=0.966, hr="x").return_dict(),
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


# Per-mode base/feature split. A forced-"?" mode is base-heavy; a richer-scatter mode is feature-heavy.
# First-pass targets — retune against the PAR sheet.
_BASE_SPLIT = {
    "base": (0.466, 0.5),
    "chance3x": (0.30, 0.666),
    "mysteryChance": (0.60, 0.366),
}


class OptimizationSetup:
    def __init__(self, game_config):
        self.game_config = game_config
        opt_params = {}
        for bm in game_config.bet_modes:
            name, wincap = bm.get_name(), bm.get_wincap()
            if bm.get_buybonus():
                opt_params[name] = _buy_params(wincap, bm.get_cost())
            else:
                base_rtp, free_rtp = _BASE_SPLIT.get(name, (0.466, 0.5))
                opt_params[name] = _base_like_params(wincap, base_rtp, free_rtp)

        self.game_config.opt_params = opt_params
        verify_optimization_input(self.game_config, self.game_config.opt_params)
