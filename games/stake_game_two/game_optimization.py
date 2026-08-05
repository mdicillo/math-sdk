"""Optimization conditions/parameters for stake_game_two.

PLACEHOLDER targets (Milestone A) — only the base mode exists and the multiplier mechanics are not yet
built, so these per-criteria RTP splits are a starting position, not a tuned result. They are here so
the full pipeline (run.py) is wired; real tuning happens once the ladder + wheel land (Milestone B/C)
and the six modes exist (Milestone D). Not exercised by run_debug.py.
"""

from optimization_program.optimization_config import (
    ConstructScaling,
    ConstructParameters,
    ConstructConditions,
    ConstructFenceBias,
    verify_optimization_input,
)


def _base_like_params():
    return {
        "conditions": {
            "0": ConstructConditions(rtp=0, av_win=0, search_conditions=0).return_dict(),
            "freegame": ConstructConditions(
                rtp=0.497, hr=200, search_conditions={"symbol": "scatter"}
            ).return_dict(),
            "basegame": ConstructConditions(hr=3.0, rtp=0.47).return_dict(),
        },
        "scaling": ConstructScaling(
            [
                {"criteria": "basegame", "scale_factor": 1.2, "win_range": (1, 5), "probability": 1.0},
                {"criteria": "freegame", "scale_factor": 1.2, "win_range": (20, 200), "probability": 1.0},
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


class OptimizationSetup:
    def __init__(self, game_config):
        self.game_config = game_config
        opt_params = {}
        for bm in game_config.bet_modes:
            opt_params[bm.get_name()] = _base_like_params()

        self.game_config.opt_params = opt_params
        verify_optimization_input(self.game_config, self.game_config.opt_params)
