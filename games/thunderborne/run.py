"""Full pipeline for thunderborne: simulate every bet mode, optimize the lookup tables, publish each base-strip mode's
candidate closest to its natural line-win spread (game_selection.py), write the PAR sheet and run the RGS format checks.

Debug scale: 10,000 books a mode. Certification is 100,000 a mode, only once the user approves that run.
Books are compressed here (publish_files/books_<mode>.jsonl.zst); run_debug.py writes readable ones.
"""

from gamestate import GameState
from game_config import GameConfig
from game_optimization import BASE_TARGETS, OptimizationSetup
from game_selection import publish_closest_candidates
from optimization_program.run_script import OptimizationExecution
from utils.game_analytics.run_analysis import create_stat_sheet
from utils.rgs_verification import execute_all_tests
from src.state.run_sims import create_books
from src.write_data.write_configs import generate_configs

if __name__ == "__main__":

    num_threads = 8
    rust_threads = 8
    batching_size = 5000
    compression = True
    profiling = False

    num_sim_args = {
        "base": int(1e4),
        "base_wild_boost": int(1e4),
        "base_activate_wheel": int(1e4),
        "base_wild_boost_activate_wheel": int(1e4),
        "bonus": int(1e4),
        "super_bonus": int(1e4),
        "wheel_bonus": int(1e4),
    }

    run_conditions = {
        "run_sims": True,
        "run_optimization": True,
        "run_analysis": True,
        "run_format_checks": True,
    }
    target_modes = list(num_sim_args.keys())

    config = GameConfig()
    gamestate = GameState(config)
    if run_conditions["run_optimization"] or run_conditions["run_analysis"]:
        optimization_setup_class = OptimizationSetup(config)

    if run_conditions["run_sims"]:
        create_books(
            gamestate,
            config,
            num_sim_args,
            batching_size,
            num_threads,
            compression,
            profiling,
        )

    generate_configs(gamestate)

    if run_conditions["run_optimization"]:
        OptimizationExecution().run_all_modes(config, target_modes, rust_threads)
        publish_closest_candidates(config, [mode for mode in target_modes if mode in BASE_TARGETS])
        generate_configs(gamestate)

    if run_conditions["run_analysis"]:
        custom_keys = [{"symbol": "scatter"}, {"wild_strike": "basegame"}, {"wild_strike": "freegame"}]
        create_stat_sheet(gamestate, custom_keys=custom_keys)

    if run_conditions["run_format_checks"]:
        execute_all_tests(config)
