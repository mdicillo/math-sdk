"""Per-mode optimization targets for skull_raiders.

Every bet mode targets 96% RTP = the sum of its per-criteria `rtp` (verify_optimization_input enforces
the sum). Each criteria gets weight-mass 1/hr and its books are tuned to average av_win = hr*rtp*cost,
so the criteria contributes exactly rtp.

CRITICAL — criteria bucketing (docs/math_docs/optimization_section + gamestate_section/force_info.md):
the optimizer assigns each sim to a criteria by matching `search_conditions` against the sim's force
record, IN ORDER, removing claimed sims from the pool. So:
  * `wincap` first (a capped feature also matches freegame) — matched by win value (== WINCAP).
  * `freegame` matched by the scatter record ({"symbol": "scatter"}, from run_freespin_from_base).
  * `wheel`    matched by the wheel record ({"symbol": "wheel"}, from run_wheel_round).
  * `0`        matched by win value (== 0).
  * `basegame` LAST with NO search_conditions — the remainder (base line wins). If it were placed before
    freegame/wheel it would greedily claim their sims (they'd optimize to ~0 and the mode collapses —
    the bug that made the base modes land at 0.35 instead of 0.96).

RTP split mirrors the TS design's base-mode economics: base line ~30% / bonus feature ~43% / raid wheel
~23% of the 96%. Antes keep base-line + the non-advertised feature at natural rates and push the rest
into the advertised feature (freegame for bonus, wheel for wheel); the combined mode boosts both.
In-pool average-win bands: basegame ~0.9x, freegame ~90-110x, wheel ~40-50x, wincap 10000x.
"""

from optimization_program.optimization_config import (
    ConstructScaling,
    ConstructParameters,
    ConstructConditions,
    verify_optimization_input,
)

WINCAP = 10000.0
SCATTER = {"symbol": "scatter"}
WHEEL = {"symbol": "wheel"}


def _cc(**kw):
    return ConstructConditions(**kw).return_dict()


def _params(test_spins, test_weights):
    return ConstructParameters(
        num_show=5000,
        num_per_fence=10000,
        min_m2m=3,
        max_m2m=8,
        pmb_rtp=1.0,
        sim_trials=5000,
        test_spins=test_spins,
        test_weights=test_weights,
        score_type="rtp",
    ).return_dict()


class OptimizationSetup:
    def __init__(self, game_config):
        self.game_config = game_config

        def base_conditions(bg_rtp, bg_hr, fg_rtp, fg_hr, wh_rtp, wh_hr):
            # Insertion order IS the bucketing order: wincap, freegame, wheel, 0, basegame(remainder).
            return {
                "wincap": _cc(rtp=0.002, av_win=WINCAP, search_conditions=WINCAP),
                "freegame": _cc(rtp=fg_rtp, hr=fg_hr, search_conditions=SCATTER),
                "wheel": _cc(rtp=wh_rtp, hr=wh_hr, search_conditions=WHEEL),
                "0": _cc(rtp=0.0, av_win=0, search_conditions=0),
                "basegame": _cc(rtp=bg_rtp, hr=bg_hr),
            }

        def buy_conditions(freegame_rtp):
            return {
                "wincap": _cc(rtp=0.002, av_win=WINCAP, search_conditions=WINCAP),
                "freegame": _cc(rtp=freegame_rtp, hr="x", search_conditions=SCATTER),
            }

        no_scaling = ConstructScaling([]).return_dict()
        base_p = _params([50, 100, 200], [0.3, 0.4, 0.3])
        buy_p = _params([10, 20, 50], [0.6, 0.2, 0.2])

        def base_mode(conds):
            return {"conditions": conds, "scaling": no_scaling, "parameters": base_p}

        def buy_mode(fg_rtp):
            return {"conditions": buy_conditions(fg_rtp), "scaling": no_scaling, "parameters": buy_p}

        self.game_config.opt_params = {
            # base (cost 1): faithful 0.302 / 0.427 / 0.229 split (base line / feature / wheel).
            "base": base_mode(base_conditions(0.302, 3.0, 0.427, 210, 0.229, 184)),
            # bonus ante (cost 3): base line + wheel at natural rates, feature boosted (hr 46 ~ 0.0216).
            "base_bonuschance": base_mode(base_conditions(0.1007, 3.0, 0.781, 46, 0.0763, 184)),
            # wheel ante (cost 5): base line + feature at natural rates, wheel boosted (hr 10 ~ 0.0987).
            "base_wheelchance": base_mode(base_conditions(0.0604, 3.0, 0.0854, 210, 0.8122, 10)),
            # combined ante (cost 8): both boosted (freegame hr 46, wheel hr 10).
            "base_bonuschance_wheelchance": base_mode(base_conditions(0.0378, 3.0, 0.2952, 46, 0.625, 10)),
            "bonus_1": buy_mode(0.958),
            "bonus_2": buy_mode(0.958),
            "bonus_mystery": buy_mode(0.958),
        }

        verify_optimization_input(self.game_config, self.game_config.opt_params)
