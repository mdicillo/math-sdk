from game_executables import GameExecutables
from src.calculations.statistics import get_random_outcome
from src.calculations.symbol import SymbolDefinition
from src.events.events import fs_trigger_event


class GameStateOverride(GameExecutables):
    """
    This class is is used to override or extend universal state.py functions.
    e.g: A specific game may have custom book properties to reset
    """

    def create_symbol_map(self):
        """Register the FIRSTAID mystery symbol. The framework derives its symbol set from `paytable` +
        `special_symbols` only, and `create_symbol` raises for anything else — but FIRSTAID lands on the
        base/ante reels (no pays, not special) and must exist on the drawn board until reveal_mystery
        replaces it. Add it as a plain non-paying definition (paytable=None)."""
        super().create_symbol_map()
        tile = getattr(self.config, "mystery_symbol", None)
        if tile and tile not in self.symbol_storage.symbol_defs:
            self.symbol_storage.symbol_defs[tile] = SymbolDefinition(tile, self.config, None)

    def reset_book(self):
        super().reset_book()
        self.fs_tier = 1

    def draw_board(self, emit_event: bool = True, trigger_symbol: str = "scatter") -> None:
        """Draw + reveal, then attach this spin's merit badge to the reveal as `wildMultiplier` — the
        client's badge rail lights it on every reveal (base and free, incl. losing/no-wild spins),
        matching our internal `reveal.wildMultiplier`. `self.spin_badge` is rolled before draw_board
        (see gamestate), so it is set by the time reveal_event has run."""
        super().draw_board(emit_event=emit_event, trigger_symbol=trigger_symbol)
        if emit_event:
            self.book.events[-1]["wildMultiplier"] = getattr(self, "spin_badge", 1)

    def update_freespin_amount(self, scatter_key: str = "scatter") -> None:
        """Set the feature TIER + total spins at the initial trigger. Tier is fixed by the trigger's
        scatter count (3/4/5 → tier 1/2/3) and drives maxHands (3/4/5) + the badge floor (1×/3×/5×).

        Natural triggers (base/ante, NOT buys) roll the "Dig Deeper" tier upgrade — a weighted promotion
        (~95% none / ~4% +1 / ~1% +2). Buys get exactly the tier they paid for. Total spins come from the
        (possibly upgraded) tier, not the raw scatter count. Retriggers add spins but never change tier."""
        base_tier = max(1, min(3, self.count_special_symbols(scatter_key) - 2))
        if self.get_current_betmode().get_buybonus():
            tier = base_tier
        else:
            tier = min(3, base_tier + int(get_random_outcome(self.config.tier_upgrade)))
        self.fs_tier = tier
        self.tot_fs = self.config.tier_spins[tier]
        basegame_trigger = self.gametype == self.config.basegame_type
        fs_trigger_event(self, basegame_trigger=basegame_trigger, freegame_trigger=not basegame_trigger)
        # Enrich the trigger so the client can build both its bonusTrigger and bonusStart from one event:
        # tier, scatter count, the pre-upgrade tier (only when "Dig Deeper" promoted it), the tier's hand
        # cap, and the badge FLOOR (present only on tiers that floor — tier 1 re-rolls freely).
        ev = self.book.events[-1]
        ev["level"] = tier
        ev["count"] = int(self.count_special_symbols(scatter_key))
        if base_tier < tier:
            ev["baseLevel"] = base_tier
        ev["maxHands"] = self.config.hands_max_by_tier[tier]
        floor = self.config.tier_floor.get(tier, 1)
        if floor > 1:
            ev["multiplier"] = floor

    def update_fs_retrigger_amt(self, scatter_key: str = "scatter") -> None:
        """Retrigger during the feature: add spins, then enrich the emitted freeSpinRetrigger so the
        client can build our bonusRetrigger. `added` is the delta from the base award. `capped` reflects
        the SDK's ACTUAL behavior — the base retrigger does NOT enforce `bonus_max`, so it is always
        False here (kept faithful to the certified math; do not wire the cap without re-certifying)."""
        before = self.tot_fs
        super().update_fs_retrigger_amt(scatter_key)
        ev = self.book.events[-1]
        ev["level"] = self.fs_tier
        ev["added"] = int(self.tot_fs - before)
        ev["capped"] = False

    def update_freespin(self) -> None:
        """Per-spin counter update; attach the cumulative feature win so the client's bonusUpdate can
        show the running feature total (book units, 100 = 1.00×)."""
        super().update_freespin()
        self.book.events[-1]["totalWin"] = int(
            round(min(self.win_manager.freegame_wins, self.config.wincap) * 100, 0)
        )

    def end_freespin(self) -> None:
        """Feature end; attach the tier and the wincap flag so the client's bonusEnd can pick the MAX
        WIN outro when the round maxed out."""
        super().end_freespin()
        ev = self.book.events[-1]
        ev["level"] = self.fs_tier
        ev["maxWin"] = bool(self.wincap_triggered)

    def assign_special_sym_function(self):
        self.special_symbol_functions = {
            "W": [self.assign_mult_property],
        }

    def assign_mult_property(self, symbol) -> dict:
        """Our merit badge is a single WHOLE-SPIN multiplier (applied in evaluate_lines_board), NOT a
        per-wild multiplier, so individual wilds carry no multiplier (kept at 1x)."""
        symbol.assign_attribute({"multiplier": 1})

    def check_repeat(self):
        super().check_repeat()
        if self.repeat is False:
            win_criteria = self.get_current_betmode_distributions().get_win_criteria()
            if win_criteria is not None and self.final_win != win_criteria:
                self.repeat = True
                return
            if win_criteria is None and self.final_win == 0:
                self.repeat = True
                return
