"""Debug run for stake_game_two — sims only, uncompressed, no optimizer (no Rust needed).

Use this to verify the ways + cascade math and the UNITS before wiring the optimizer. Books land as a
plain JSON array in library/books/books_<mode>.json.
"""

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
        "base": 2000,
        "chance3x": 2000,
        "mysteryChance": 2000,
        "bonus": 1000,
        "super_bonus": 1000,
        "mystery_bonus": 1000,
    }
    config = GameConfig()
    gamestate = GameState(config)
    create_books(gamestate, config, num_sim_args, batching_size, num_threads, compression, profiling)
    generate_configs(gamestate)
