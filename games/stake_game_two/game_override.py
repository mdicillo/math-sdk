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
        """Per free spin: annotate the emitted event with the ladder value this spin STARTS at — the
        carried feature ladder for a persistent run, or 1 for an untilUpgrade tier that hasn't upgraded
        yet. Purely observational (the ladder is set in run_freespin right after)."""
        super().update_freespin()
        start = self.feature_ladder if getattr(self, "fs_persistent", False) else 1
        self.book.events[-1]["startMultiplier"] = int(start)

    def update_freespin_amount(self, scatter_key: str = "scatter"):
        """Set the feature TIER + initial spins at the trigger. Tier is fixed by the scatter count
        (3/4/5 -> t1/t2/t3) and drives persistence, the tier-3 opening wheel spin, and (via the buys,
        Milestone D) the feature reel. The ladder itself always climbs +1 per tumble. Retriggers add
        spins but never change the tier."""
        count = self.count_special_symbols(scatter_key)
        tier = self.config.bonus_tiers[count]
        self.fs_tier = tier["level"]
        self.fs_persistence = tier["persistence"]
        self.fs_opening_wheel_spins = tier["opening_wheel_spins"]
        super().update_freespin_amount(scatter_key)  # sets tot_fs from freespin_triggers + emits trigger
        # Enrich the trigger event so a client can build its bonus start from one event.
        ev = self.book.events[-1]
        ev["level"] = self.fs_tier
        ev["count"] = int(count)

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
