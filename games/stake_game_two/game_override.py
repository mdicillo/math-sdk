from game_executables import GameExecutables
from src.calculations.symbol import SymbolDefinition
from src.events.events import fs_trigger_event, reveal_event


class GameStateOverride(GameExecutables):
    """Override / extend universal state.py behaviour for this game."""

    def reset_book(self):
        """Clear per-round feature state so a stale tier/reel can't leak from a previous simulation."""
        super().reset_book()
        self.fs_feature_reel = None
        self.fs_persistent = False
        self.upgrade_spent = False
        self.feature_ladder = 1
        self.locked_buy_count = None
        # Stake multiplier for the active mode (Mystery Chance = 50; everything else 1).
        self.bet_multiplier = self.config.mode_bet_multiplier.get(getattr(self, "betmode", None), 1)

    def draw_board(self, emit_event: bool = True, trigger_symbol: str = "scatter"):
        """Draw the board, and for a forced-"?" mode (Mystery Chance) plant the guaranteed "?" BEFORE
        the reveal event is emitted, so the reveal the client renders already shows it. Base game only —
        the feature has its own wheel activation."""
        forced = self.config.mode_forced_mystery.get(getattr(self, "betmode", None), 0)
        if forced and emit_event and self.gametype == self.config.basegame_type:
            super().draw_board(emit_event=False, trigger_symbol=trigger_symbol)
            self.plant_forced_mystery(forced)
            reveal_event(self)
        else:
            super().draw_board(emit_event=emit_event, trigger_symbol=trigger_symbol)

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
        (3/4/5 -> t1/t2/t3) and drives persistence, the tier-3 opening wheel spin, and the per-tier
        FEATURE REEL (FR1/FR0/FR3) — used for natural triggers AND buys alike (the TS provider draws
        natural features from the per-tier pool too). The ladder always climbs +1 per tumble.
        Retriggers add spins but never change the tier or the reel."""
        count = self.count_special_symbols(scatter_key)
        # A buy is locked to its bought tier (the forced opening count); a natural trigger uses the
        # accumulated final count (accumulation is what lets a cascade upgrade the tier).
        if self.get_current_betmode().get_buybonus() and getattr(self, "locked_buy_count", None):
            count = self.locked_buy_count
        count = max(3, min(5, count))
        tier = self.config.bonus_tiers[count]
        self.fs_tier = tier["level"]
        self.fs_persistence = tier["persistence"]
        self.fs_opening_wheel_spins = tier["opening_wheel_spins"]
        self.fs_feature_reel = tier["feature_reel"]
        # Set the initial spins from the (locked/accumulated) tier count and emit the trigger. Not via
        # super(), which would re-read the final accumulated count and mis-size a buy's award.
        self.tot_fs = self.config.freespin_triggers[self.gametype][count]
        basegame_trigger = self.gametype == self.config.basegame_type
        fs_trigger_event(self, basegame_trigger=basegame_trigger, freegame_trigger=not basegame_trigger)
        ev = self.book.events[-1]
        ev["level"] = self.fs_tier
        ev["count"] = int(count)

    def get_current_distribution_conditions(self) -> dict:
        """Select the per-tier FEATURE reel for free-spin board draws. Returns a shallow copy with
        reel_weights[freegame] pointed at this feature's tier reel (fs_feature_reel), so the tier a
        feature runs — whether rolled naturally or bought — determines its pool. Copy, never mutate:
        the conditions dict is shared config read concurrently across sim threads."""
        cond = super().get_current_distribution_conditions()
        if self.gametype == self.config.freegame_type and isinstance(cond, dict):
            # The wincap criteria forces the max-win tail on the hot WCAP pool; every other feature runs
            # on its tier reel (fs_feature_reel).
            reel = "WCAP" if self.criteria == "wincap" else getattr(self, "fs_feature_reel", None)
            if reel:
                cond = dict(cond)
                rw = dict(cond.get("reel_weights", {}))
                rw[self.config.freegame_type] = {reel: 1}
                cond["reel_weights"] = rw
        return cond

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
