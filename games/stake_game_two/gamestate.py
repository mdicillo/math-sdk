from game_override import GameStateOverride


class GameState(GameStateOverride):
    """Ways + cascade game logic. Base and free spins share the same tumble loop: evaluate, then keep
    tumbling while the latest board paid, until a no-win drop (or the wincap) ends the chain."""

    def run_spin(self, sim, simulation_seed=None):
        self.reset_seed(sim)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            self.draw_board()

            # Ladder: the opening board pays at 1x (reset_book sets global_multiplier=1); then every
            # winning tumble climbs it +1, so the next drop pays at 2x, 3x, … (Rage Quit's per-cascade
            # multiplier). update_global_mult increments and emits the multiplier event.
            self.get_ways_update_wins()
            self.emit_tumble_win_events()
            while self.win_data["totalWin"] > 0 and not self.wincap_triggered:
                self.update_global_mult()
                self.tumble_game_board()
                self.get_ways_update_wins()
                self.emit_tumble_win_events()

            self.set_end_tumble_event()
            self.win_manager.update_gametype_wins(self.gametype)

            if self.check_fs_condition() and self.check_freespin_entry():
                self.run_freespin_from_base()

            self.evaluate_finalwin()
            self.check_repeat()
        self.imprint_wins()

    def run_freespin(self):
        self.reset_fs_spin()
        while self.fs < self.tot_fs:
            self.update_freespin()
            self.draw_board()

            # Same per-tumble ladder as the base game. Milestone B resets the ladder each free spin
            # (update_freespin override); tier persistence (t2/t3 keep it across the feature, t1 until
            # the wheel's Upgrade) is Milestone C.
            self.get_ways_update_wins()
            self.emit_tumble_win_events()
            while self.win_data["totalWin"] > 0 and not self.wincap_triggered:
                self.update_global_mult()
                self.tumble_game_board()
                self.get_ways_update_wins()
                self.emit_tumble_win_events()

            self.set_end_tumble_event()
            # A retrigger during the feature awards a flat +5 spins (encoded on the freegame trigger row).
            if self.check_fs_condition():
                self.update_fs_retrigger_amt()

            self.win_manager.update_gametype_wins(self.gametype)
        self.end_freespin()
