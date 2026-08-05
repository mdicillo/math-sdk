from game_override import GameStateOverride


class GameState(GameStateOverride):
    """Ways + cascade game logic with the mystery "?" wheel and the three free-spins tiers.

    Base and free spins share the tumble loop (evaluate a drop, keep tumbling while it paid). The
    differences the tiers introduce live in run_freespin: the wheel always activates in free spins,
    the ladder starts persistent (t2/t3) or resets each spin until the Upgrade (t1), tier 3 opens with
    a free wheel spin, and a retrigger adds a flat +5.
    """

    def run_spin(self, sim, simulation_seed=None):
        self.reset_seed(sim)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            self.draw_board()
            # A BUY locks its tier to the scatters FORCED on the opening board — accumulation during the
            # base cascade upgrades a natural trigger but never a buy (TS: level = boughtLevel). Capture
            # the forced count before the cascade can add more.
            self.locked_buy_count = (
                self.count_special_symbols("scatter") if self.get_current_betmode().get_buybonus() else None
            )

            # Base game: the ladder opens at 1x (reset_book); a "?" activates only on a winning drop.
            # Each winning tumble climbs the ladder +1 (update_global_mult), so drops pay 1x, 2x, 3x …,
            # plus any wheel boost folded into the drop it lands on.
            self.evaluate_drop(always_activate=False)
            self.emit_tumble_win_events()
            while self.win_data["totalWin"] > 0 and not self.wincap_triggered:
                self.update_global_mult()
                self.tumble_game_board()
                self.evaluate_drop(always_activate=False)
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
        # Feature-level ladder state (tier set by update_freespin_amount at the trigger).
        self.fs_persistent = self.fs_persistence == "persistent"
        self.upgrade_spent = False
        self.feature_ladder = 1
        # Tier 3 opens with a free wheel spin, boosting the (persistent) opening ladder before spin 1.
        self.run_opening_wheels()

        while self.fs < self.tot_fs and not self.wincap_triggered:
            self.update_freespin()
            # Ladder start for this spin: a persistent feature carries the ladder; an untilUpgrade tier
            # resets to 1x each spin until the Upgrade has flipped it persistent.
            self.global_multiplier = self.feature_ladder if self.fs_persistent else 1
            self.draw_board()

            # Free spins: a "?" always activates (even on a non-winning terminal drop).
            self.evaluate_drop(always_activate=True)
            self.emit_tumble_win_events()
            while self.win_data["totalWin"] > 0 and not self.wincap_triggered:
                self.update_global_mult()
                self.tumble_game_board()
                self.evaluate_drop(always_activate=True)
                self.emit_tumble_win_events()

            self.set_end_tumble_event()
            # Carry the ladder forward (its value after this spin's cascade, including any wheel boost on
            # the resting board). A persistent feature resumes here next spin.
            self.feature_ladder = self.global_multiplier

            if not self.wincap_triggered and self.check_fs_condition():
                self.update_fs_retrigger_amt()  # flat +5 (freespin_triggers[freegame] = {3:5,4:5,5:5})

            self.win_manager.update_gametype_wins(self.gametype)

        self.end_freespin()
