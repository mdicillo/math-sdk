from game_executables import GameExecutables
from src.calculations.statistics import get_random_outcome


class GameStateOverride(GameExecutables):
    """
    This class is is used to override or extend universal state.py functions.
    e.g: A specific game may have custom book properties to reset
    """

    def reset_book(self):
        super().reset_book()

    def assign_special_sym_function(self):
        self.special_symbol_functions = {
            "W": [self.assign_mult_property],
        }

    def assign_mult_property(self, symbol) -> dict:
        """Assign a multiplier to each WILD, rolled from the active mode's per-gametype bag.

        Unlike the reference lines game (feature-only), Skull Raiders has multiplier wilds in BASE too:
        a tame bag in the base game, a fat bag in free spins. Only >=2 wilds contribute to a line (the
        "symbol" strategy sums them); a x1 wild carries no badge and adds nothing. gameConfig.ts:174-194.
        """
        mult_values = self.get_current_distribution_conditions()["mult_values"]
        bag = mult_values.get(self.gametype)
        multiplier_value = get_random_outcome(bag) if bag else 1
        symbol.assign_attribute({"multiplier": multiplier_value})

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
