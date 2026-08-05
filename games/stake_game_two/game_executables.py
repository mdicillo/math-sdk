from game_calculations import GameCalculations
from src.calculations.ways import Ways


class GameExecutables(GameCalculations):
    """Ways + cascade (tumble) executables.

    The cascade reuses the SDK's Tumble machinery (Executables.tumble_game_board /
    emit_tumble_win_events / evaluate_wincap). This class adds the ways evaluation and, crucially,
    marks the winning symbols so the tumble removes them.
    """

    def get_ways_update_wins(self):
        """Evaluate the current board for ways wins, flag winning symbols for the tumble, and update
        the win manager. The ladder is applied as a GLOBAL multiplier (self.global_multiplier); in
        Milestone A it is held at 1, so this is a plain ways evaluation.

        spin_win accumulates across the whole cascade (update_spinwin ADDS), so each tumble's win adds
        to the sequence total — exactly the cascade behaviour.
        """
        self.win_data = Ways.get_ways_data(
            self.config,
            self.board,
            global_multiplier=self.global_multiplier,
            multiplier_strategy="global",
        )
        # Flag every winning cell (including the wilds that completed a win) so tumble_board removes
        # them on the next gravity step. Scatters and an inert "?" never win, so they are never flagged
        # — matching "SCATTER never tumbles".
        for win in self.win_data["wins"]:
            for pos in win["positions"]:
                self.board[pos["reel"]][pos["row"]].explode = True

        if self.win_data["totalWin"] > 0:
            Ways.record_ways_wins(self)
            self.win_manager.update_spinwin(self.win_data["totalWin"])
        self.win_manager.tumble_win = self.win_data["totalWin"]
