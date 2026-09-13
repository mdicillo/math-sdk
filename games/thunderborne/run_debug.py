"""Debug run for thunderborne: sims only, uncompressed, no optimizer (no Rust needed).

Step 1 simulates the four base-strip modes with features off. The buys join once the free spins are ported, and
generate_configs with them (it needs every bet mode's books).
"""

from gamestate import GameState
from game_config import GameConfig
from src.state.run_sims import create_books

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
    }
    config = GameConfig()
    gamestate = GameState(config)
    create_books(gamestate, config, num_sim_args, batching_size, num_threads, compression, profiling)
