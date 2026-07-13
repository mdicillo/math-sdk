"""Debug run for camp_deadwater — sims only, uncompressed, no optimizer (no Rust needed)."""

from gamestate import GameState
from game_config import GameConfig
from src.state.run_sims import create_books
from src.write_data.write_configs import generate_configs

if __name__ == "__main__":
    num_threads = 1
    batching_size = 5000
    compression = False
    profiling = False
    num_sim_args = {
        "base": 400,
        "ante_searchparty": 400,
        "ante_allout": 400,
        "bonus_1": 300,
        "bonus_2": 300,
        "bonus_3": 300,
    }
    config = GameConfig()
    gamestate = GameState(config)
    create_books(gamestate, config, num_sim_args, batching_size, num_threads, compression, profiling)
    generate_configs(gamestate)
