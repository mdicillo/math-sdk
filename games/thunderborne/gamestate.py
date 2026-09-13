from game_override import GameStateOverride
from src.events.events import reveal_event


class GameState(GameStateOverride):
    """Handles game logic and events for a single simulation number/game-round."""

    def run_spin(self, sim, simulation_seed=None):
        self.reset_seed(sim)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            # Free spins are still off: boards are drawn straight from the strips (every stop equally likely), not with
            # draw_board, which re-draws base boards showing 3 scatters unless the criteria forces free spins.
            self.create_board_reelstrips()
            reveal_event(self)

            # WILD STRIKE: the frame settles, beaming WILDs may strike, then the lines evaluate with the new wilds.
            strike = self.get_current_distribution_conditions()["wild_strike"]
            self.place_wild_frame(strike)
            self.run_wild_strike(strike)

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
