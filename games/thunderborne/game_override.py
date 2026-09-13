from game_executables import GameExecutables


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

    def assign_special_sym_function(self):
        # Naturally landed base-game WILDs keep the SDK's default multiplier of 1 (no line multiplier). WILD STRIKE
        # wilds get theirs when they're struck (game_calculations strike_wild).
        self.special_symbol_functions = {}
