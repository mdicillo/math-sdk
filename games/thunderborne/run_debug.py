"""Debug run for thunderborne: sims only, uncompressed, no optimizer (no Rust needed).

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
    num_sim_args = {
        "base": int(1e4),
        "base_wild_boost": int(1e4),
        "base_activate_wheel": int(1e4),
        "base_wild_boost_activate_wheel": int(1e4),
        "bonus": int(1e4),
        "super_bonus": int(1e4),
        "wheel_bonus": int(1e4),
    }
    config = GameConfig()
    gamestate = GameState(config)
    create_books(gamestate, config, num_sim_args, batching_size, num_threads, compression, profiling)
    generate_configs(gamestate)
