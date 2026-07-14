from game_override import GameStateOverride


class GameState(GameStateOverride):
    """Handles game logic and events for a single simulation number/game-round."""

    def run_spin(self, sim, simulation_seed=None):
        self.reset_seed(sim)
        self.repeat = True
        while self.repeat:
            self.reset_book()

            # Roll this spin's merit badge (live in the base game too) BEFORE drawing, so the reveal
            # event can carry it (draw_board -> reveal_event; see the draw_board override that attaches
            # `wildMultiplier`). Then evaluate.
            self.spin_badge = self.roll_merit_badge()
            self.draw_board()
            self.evaluate_lines_board()

            self.win_manager.update_gametype_wins(self.gametype)
            if self.check_fs_condition():
                self.run_freespin_from_base()

            self.evaluate_finalwin()
            self.check_repeat()
        self.imprint_wins()

    def run_freespin(self):
        self.reset_fs_spin()
        while self.fs < self.tot_fs:
            self.update_freespin()

            # One badge per free spin, shared by the natural and (if it fires) the tumbled board.
            # Rolled BEFORE drawing so the reveal event carries it (see the draw_board override).
            self.spin_badge = self.roll_merit_badge()
            self.draw_board()

            # Natural pre-grab board pays first.
            self.evaluate_lines_board()
            # Helping Hands: on a trigger, zombie hands clear + tumble the board (wilds preserved), then
            # the tumbled board's win is ADDED to the natural win (spin_win accumulates across both).
            if self.maybe_run_hands():
                self.evaluate_lines_board()

            if self.check_fs_condition():
                self.update_fs_retrigger_amt()

            self.win_manager.update_gametype_wins(self.gametype)

        self.end_freespin()
