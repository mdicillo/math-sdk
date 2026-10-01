"""Debug run for sheriff_showdown: sims only, uncompressed (no Rust needed), 10,000 books a mode, then the published
weights (weights.py) and the config files (config.json, config_fe, index.json).
"""

import os

os.environ.setdefault("SHERIFF_BOOKS", "10000")

from gamestate import GameState  # noqa: E402
from game_config import GameConfig  # noqa: E402
from src.state.run_sims import create_books  # noqa: E402
from src.write_data.write_configs import generate_configs  # noqa: E402
import weights  # noqa: E402

if __name__ == "__main__":
    num_threads = 8
    batching_size = 5000
    compression = False
    profiling = False
    config = GameConfig()
    num_sim_args = {mode.get_name(): int(os.environ["SHERIFF_BOOKS"]) for mode in config.bet_modes}
    gamestate = GameState(config)
    create_books(gamestate, config, num_sim_args, batching_size, num_threads, compression, profiling)
    weights.main(list(num_sim_args))
    generate_configs(gamestate)
