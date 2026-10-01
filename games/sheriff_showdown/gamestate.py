"""Sheriff Showdown game state: plays one round per simulation and writes its book (the client's
src/rgs/sheriff/provider.ts round() + BookBuilder)."""

from src.state.state import GeneralGameState

import spec
from game_calculations import play_reel_spin
from game_events import final_win_event, reveal_event, set_total_win_event, to_units, win_info_event


class GameState(GeneralGameState):
    """Handles game logic and events for a single simulation number/game-round."""

    def assign_special_sym_function(self):
        # The game's boards are plain symbol ids (game_calculations.py); the SDK's symbol objects aren't used.
        self.special_symbol_functions = {}

    def reset_book(self):
        super().reset_book()
        # The round's running total in book units, clamped at the max win (WINCAP_X x 100).
        self.total_units = 0
        self.cap_units = to_units(spec.WINCAP_X)

    @property
    def capped(self) -> bool:
        return self.total_units >= self.cap_units

    def pay(self, units: int) -> int:
        """Add an award to the round, clamped to the max win. Returns the amount actually paid (book units)."""
        paid = min(units, max(0, self.cap_units - self.total_units))
        self.total_units += paid
        self.win_manager.update_spinwin(paid / 100)
        return paid

    def run_spin(self, sim, simulation_seed=None):
        self.reset_seed(sim)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            mode = spec.BASE_MODES[self.betmode]
            strip_id = mode["strips"]
            result = play_reel_spin(strip_id, spec.STRIPS[strip_id], spec.CLEAN_STOPS[strip_id])
            self.reel_spin(result)
            if self.total_units > 0:
                set_total_win_event(self, self.total_units)
            self.win_manager.update_gametype_wins(self.gametype)

            self.update_final_win()
            final_win_event(self, self.total_units, self.capped)
            self.check_repeat()
        self.imprint_wins()

    def reel_spin(self, result: dict) -> int:
        """One normal reel spin's events: reveal, then winInfo with what the spin added to the round."""
        self.win_manager.reset_spin_win()
        reveal_event(self, result)
        total = to_units(result["scatter"]["payX"]) + sum(to_units(line["payX"]) for line in result["lines"])
        paid = self.pay(total)
        win_info_event(self, result, paid)
        return paid

    def run_freespin(self):
        """Free spins arrive in a later port step."""
        raise NotImplementedError
