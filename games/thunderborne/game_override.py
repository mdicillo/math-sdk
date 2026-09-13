from game_executables import GameExecutables
from game_config import FEATURE_WILD_MULT, MAX_FREE_SPINS, RETRIGGER_SPINS
from game_events import wheel_spin_event
from src.events.events import fs_trigger_event


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
        """Trigger the feature: in ACTIVATE WHEEL modes the wheel spins first and sets every WILD's multiplier, otherwise
        WILDs are FEATURE_WILD_MULT."""
        self.record(
            {
                "kind": self.count_special_symbols(scatter_key),
                "symbol": scatter_key,
                "gametype": self.gametype,
            }
        )
        if self.get_current_distribution_conditions()["wheel"]:
            self.feature_mult = self.wheel_mult
            wheel_spin_event(self)
        else:
            self.feature_mult = FEATURE_WILD_MULT
        self.update_freespin_amount()
        self.run_freespin()

    def update_fs_retrigger_amt(self, scatter_key: str = "scatter") -> None:
        """Retrigger: RETRIGGER_SPINS more free spins, never past MAX_FREE_SPINS."""
        self.tot_fs = min(self.tot_fs + RETRIGGER_SPINS, MAX_FREE_SPINS)
        fs_trigger_event(self, freegame_trigger=True, basegame_trigger=False)

    def check_repeat(self):
        super().check_repeat()
        # Every feature has at least one WILD STRIKE and pays at least its floor; a round whose feature doesn't is played
        # again (the base spin is drawn independently of the feature, so only the feature's outcome is filtered).
        if self.repeat is False and self.triggered_freegame:
            floor = self.get_current_distribution_conditions()["feature_floor"]
            if self.feature_strikes == 0 or self.win_manager.freegame_wins < floor:
                self.repeat = True
