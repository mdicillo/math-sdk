"""Debug run for sheriff_showdown: sims only, uncompressed, no optimizer (no Rust needed).

Every bet mode, then the config files (config.json, config_fe, index.json) from the unweighted lookup tables.
"""

from gamestate import GameState
from game_config import GameConfig
from src.state.run_sims import create_books
from src.write_data.write_configs import generate_configs

if __name__ == "__main__":
    num_threads = 8
    batching_size = 5000
    compression = False
    profiling = False
    num_sim_args = {mode.get_name(): int(1e4) for mode in GameConfig().bet_modes}
    config = GameConfig()
    gamestate = GameState(config)
    create_books(gamestate, config, num_sim_args, batching_size, num_threads, compression, profiling)
    generate_configs(gamestate)
