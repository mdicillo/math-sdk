"""Full pipeline for sheriff_showdown: books for every bet mode (compressed), the published weights (weights.py -
exact category probabilities, in place of the optimizer), the config files, the PAR sheet and the RGS format checks.

Certification scale: 100,000 books a mode (SHERIFF_BOOKS overrides it, e.g. for a quick end-to-end check).
"""

import os

os.environ.setdefault("SHERIFF_BOOKS", "100000")

from gamestate import GameState  # noqa: E402
from game_config import GameConfig  # noqa: E402
from src.state.run_sims import create_books  # noqa: E402
from src.write_data.write_configs import generate_configs  # noqa: E402
from utils.game_analytics.run_analysis import create_stat_sheet  # noqa: E402
from utils.rgs_verification import execute_all_tests  # noqa: E402
import weights  # noqa: E402

if __name__ == "__main__":
    num_threads = 8
    # One batch a mode: the SDK freezes a mode's force-record keys after its first batch, and a key first recorded in
    # a later batch then fails (src/config/betmode.py add_force_key on a tuple).
    batching_size = int(os.environ["SHERIFF_BOOKS"]) // num_threads
    compression = True
    profiling = False

    config = GameConfig()
    num_sim_args = {mode.get_name(): int(os.environ["SHERIFF_BOOKS"]) for mode in config.bet_modes}
    run_conditions = {"run_sims": True, "run_weights": True, "run_analysis": True, "run_format_checks": True}

    gamestate = GameState(config)
    if run_conditions["run_sims"]:
        create_books(gamestate, config, num_sim_args, batching_size, num_threads, compression, profiling)
    generate_configs(gamestate)
    if run_conditions["run_weights"]:
        weights.main(list(num_sim_args))
        generate_configs(gamestate)
    if run_conditions["run_analysis"]:
        custom_keys = [{"bonus": "sheriff"}, {"bonus": "posse"}, {"bonus": "showdown"}, {"showdown": "X"}]
        create_stat_sheet(gamestate, custom_keys=custom_keys)
    if run_conditions["run_format_checks"]:
        execute_all_tests(config)
