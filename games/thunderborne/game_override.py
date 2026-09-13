from game_executables import GameExecutables
from game_config import FEATURE_WILD_MULT, MAX_FREE_SPINS, RETRIGGER_SPINS
from game_events import wheel_spin_event
from src.events.events import fs_trigger_event, wincap_event


class GameStateOverride(GameExecutables):
    """
    This class is is used to override or extend universal state.py functions.
    e.g: A specific game may have custom book properties to reset
    """

    def reset_book(self):
        super().reset_book()
        # WILD STRIKE: the frame's cell, the WILDs beaming from it, and the strike's new wilds for this spin.
        self.frame_cell = None
        self.beams = []
        self.strike_wilds = []
        # Free spins: the natural WILDs' multiplier and how many strikes the feature has had.
        self.feature_mult = FEATURE_WILD_MULT
        self.feature_strikes = 0

    def assign_special_sym_function(self):
        self.special_symbol_functions = {"W": [self.assign_wild_mult]}

    def assign_wild_mult(self, symbol):
        """Naturally landed WILDs: 1x in the base game, the feature's multiplier in free spins. WILD STRIKE wilds get
        their own multiplier when they're struck (game_calculations strike_wild)."""
        mult = self.feature_mult if self.gametype == self.config.freegame_type else 1
        symbol.assign_attribute({"multiplier": mult})

    def run_freespin_from_base(self, scatter_key: str = "scatter") -> None:
        """Trigger the feature: when the mode plays the wheel it spins first and sets every WILD's multiplier, otherwise
        WILDs take the mode's feature_mult (2x, or 3x in SUPER BONUS)."""
        self.record(
            {
                "kind": self.count_special_symbols(scatter_key),
                "symbol": scatter_key,
                "gametype": self.gametype,
            }
        )
        conditions = self.get_current_distribution_conditions()
        if conditions["wheel"]:
            self.feature_mult = self.wheel_mult
            wheel_spin_event(self)
        else:
            self.feature_mult = conditions["feature_mult"]
        self.update_freespin_amount()
        self.run_freespin()

    def update_freespin_amount(self, scatter_key: str = "scatter") -> None:
        """A trigger's free spins: the mode's free_spins (20 in SUPER BONUS, otherwise 10)."""
        self.tot_fs = self.get_current_distribution_conditions()["free_spins"]
        fs_trigger_event(self, basegame_trigger=True, freegame_trigger=False)

    def update_fs_retrigger_amt(self, scatter_key: str = "scatter") -> None:
        """Retrigger: RETRIGGER_SPINS more free spins, never past MAX_FREE_SPINS."""
        self.tot_fs = min(self.tot_fs + RETRIGGER_SPINS, MAX_FREE_SPINS)
        fs_trigger_event(self, freegame_trigger=True, basegame_trigger=False)

    def check_repeat(self):
        super().check_repeat()
        # Every feature has at least one WILD STRIKE and pays at least its floor; a round whose feature doesn't is played
        # again (the base spin is drawn independently of the feature, so only the feature's outcome is filtered).
        # Wins are rounded to hundredths before comparing: the SDK sums line wins as floats.
        if self.repeat is False and self.triggered_freegame:
            floor = self.get_current_distribution_conditions()["feature_floor"]
            if self.feature_strikes == 0 or round(self.win_manager.freegame_wins, 2) < floor:
                self.repeat = True

    def evaluate_wincap(self) -> None:
        """Stop the round's spins once its win reaches the wincap (Executables.evaluate_wincap), with the running win
        rounded to hundredths so a round summing to 4999.99999... still caps."""
        if round(self.win_manager.running_bet_win, 2) >= self.config.wincap and not self.wincap_triggered:
            self.wincap_triggered = True
            wincap_event(self)
            return True
        return False
