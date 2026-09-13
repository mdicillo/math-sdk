from game_executables import GameExecutables


class GameStateOverride(GameExecutables):
    """
    This class is is used to override or extend universal state.py functions.
    e.g: A specific game may have custom book properties to reset
    """

    def reset_book(self):
        super().reset_book()

    def assign_special_sym_function(self):
        # Naturally landed WILDs keep the SDK's default multiplier of 1 (no line multiplier) until WILD STRIKE is ported.
        self.special_symbol_functions = {}
