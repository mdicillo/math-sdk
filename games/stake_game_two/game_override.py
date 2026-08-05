from game_executables import GameExecutables
from src.calculations.symbol import SymbolDefinition


class GameStateOverride(GameExecutables):
    """Override / extend universal state.py behaviour for this game."""

    def create_symbol_map(self):
        """Register the mystery "?" tile ("M"). The framework derives its symbol set from `paytable` +
        `special_symbols` only, and `create_symbol` raises for anything else — but "M" lands on the
        reels (no pays, not special) and must exist on the drawn board. Add it as a plain non-paying
        definition (paytable=None). Mirrors camp_deadwater's FIRSTAID registration."""
        super().create_symbol_map()
        tile = getattr(self.config, "mystery_symbol", None)
        if tile and tile not in self.symbol_storage.symbol_defs:
            self.symbol_storage.symbol_defs[tile] = SymbolDefinition(tile, self.config, None)

    def assign_special_sym_function(self):
        # No per-symbol functions: the ladder is a whole-board global multiplier, and the mystery wheel
        # is applied in the tumble loop, not attached to a drawn symbol.
        self.special_symbol_functions = {}

    def update_freespin(self):
        """Per free spin: reset the ladder to 1x. Milestone B treats every tier the same (reset each
        spin); Milestone C makes this tier-dependent — tiers 2/3 persist the ladder across the whole
        feature, and tier 1 persists once the wheel's Upgrade lands."""
        super().update_freespin()
        self.global_multiplier = 1

    def check_repeat(self):
        """Verify the simulation satisfied its distribution/criteria constraints; if not, resample.

        Mirrors the reference cascade games: a win_criteria must be met exactly, a forced freegame must
        have triggered, and a non-"0" criteria must have produced a win.
        """
        super().check_repeat()
        if self.repeat is False:
            win_criteria = self.get_current_betmode_distributions().get_win_criteria()
            if win_criteria is not None and self.final_win != win_criteria:
                self.repeat = True
                return
            if self.get_current_distribution_conditions()["force_freegame"] and not self.triggered_freegame:
                self.repeat = True
                return
            if self.win_manager.running_bet_win == 0 and self.criteria != "0":
                self.repeat = True
                return
