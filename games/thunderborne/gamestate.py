import random
from game_override import GameStateOverride
from game_config import MAX_FREE_SPINS, WHEEL_WEIGHTS
from src.calculations.statistics import get_random_outcome
from src.events.events import reveal_event


class GameState(GameStateOverride):
    """Handles game logic and events for a single simulation number/game-round."""

    def run_spin(self, sim, simulation_seed=None):
        self.reset_seed(sim)
        # The wheel (ACTIVATE WHEEL modes) spins once a round: a round played again for its feature's rules keeps the
        # wheel's multiplier, as the fake math replays only the feature.
        self.wheel_mult = get_random_outcome(WHEEL_WEIGHTS)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            # "freegame" / "wincap" books force 3 BONUS symbols; every other book re-draws any board showing them.
            self.draw_board()

            # WILD STRIKE: the frame settles, beaming WILDs may strike, then the lines evaluate with the new wilds.
            strike = self.get_current_distribution_conditions()["wild_strike"]
            self.place_wild_frame(strike)
            self.run_wild_strike(strike)
            self.base_strike = bool(self.strike_wilds)

            # Evaluate wins, update wallet, transmit events
            self.evaluate_lines_board()

            self.win_manager.update_gametype_wins(self.gametype)
            if self.check_fs_condition():
                self.run_freespin_from_base()

            self.evaluate_finalwin()
            self.check_repeat()
        self.imprint_wins()

    def run_freespin(self):
        self.reset_fs_spin()
        strike = self.get_current_distribution_conditions()["free_strike"]
        # Every feature's first WILD STRIKE is guaranteed: if none has come by a random spin among its first spins, that
        # spin (or the next one a strike fits) lands a WILD in the frame, planting one if none landed, and strikes.
        guaranteed_spin = random.randint(1, self.tot_fs)
        while self.fs < self.tot_fs and not self.wincap_triggered:
            self.update_freespin()
            must_strike = self.feature_strikes == 0 and self.fs >= guaranteed_spin
            self.draw_board(emit_event=False)
            if must_strike:
                self.ensure_wild()
            reveal_event(self)

            self.place_wild_frame(strike, on_wild=must_strike)
            self.run_wild_strike(strike, certain=must_strike)
            if self.strike_wilds:
                self.feature_strikes += 1

            self.evaluate_lines_board()

            # Retrigger after the spin's win events, up to MAX_FREE_SPINS.
            if self.check_fs_condition() and self.tot_fs < MAX_FREE_SPINS:
                self.update_fs_retrigger_amt()

            self.win_manager.update_gametype_wins(self.gametype)

        self.end_freespin()
