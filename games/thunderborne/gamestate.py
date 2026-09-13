from game_override import GameStateOverride
from src.events.events import reveal_event


class GameState(GameStateOverride):
    """Handles game logic and events for a single simulation number/game-round."""

    def run_spin(self, sim, simulation_seed=None):
        self.reset_seed(sim)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            # Step 1: features off. Boards are drawn straight from the strips (every stop equally likely), not with
            # draw_board, which re-draws base boards showing 3 scatters unless the criteria forces free spins.
            self.create_board_reelstrips()
            reveal_event(self)

            # Evaluate wins, update wallet, transmit events
            self.evaluate_lines_board()

            self.win_manager.update_gametype_wins(self.gametype)

            self.evaluate_finalwin()
            self.check_repeat()
        self.imprint_wins()

    def run_freespin(self):
        # Free spins are ported in a later step.
        self.reset_fs_spin()
        while self.fs < self.tot_fs:
            self.update_freespin()

        self.end_freespin()
