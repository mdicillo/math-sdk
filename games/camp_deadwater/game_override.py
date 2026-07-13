from game_executables import GameExecutables
from src.calculations.statistics import get_random_outcome
from src.events.events import fs_trigger_event


class GameStateOverride(GameExecutables):
    """
    This class is is used to override or extend universal state.py functions.
    e.g: A specific game may have custom book properties to reset
    """

    def reset_book(self):
        super().reset_book()
        self.fs_tier = 1

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
