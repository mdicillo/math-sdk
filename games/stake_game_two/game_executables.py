from game_calculations import GameCalculations
from src.calculations.ways import Ways


class GameExecutables(GameCalculations):
    """Ways + cascade (tumble) executables.

    The cascade reuses the SDK's Tumble machinery (Executables.tumble_game_board /
    emit_tumble_win_events / evaluate_wincap). This class adds the ways evaluation and, crucially,
    marks the winning symbols so the tumble removes them.
    """

    def get_ways_update_wins(self):
        """Evaluate the current board for ways wins, add WILD's flat pay, flag winning symbols for the
        tumble, and update the win manager. The ladder is applied as a GLOBAL multiplier
        (self.global_multiplier), which the caller climbs by +1 per winning tumble.

        spin_win accumulates across the whole cascade (update_spinwin ADDS), so each tumble's win adds
        to the sequence total — exactly the cascade behaviour.
        """
        self.win_data = Ways.get_ways_data(
            self.config,
            self.board,
            global_multiplier=self.global_multiplier,
            multiplier_strategy="global",
        )
        # WILD flat pay (Milestone B): stacks on top of the ways wins the same wilds complete.
        self.add_wild_pay()
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

    def add_wild_pay(self):
        """WILD's own pay: a flat `config.wild_pay` (x total bet) awarded ONCE when a wild sits on ALL
        five reels, multiplied by the current ladder (global_multiplier) but NOT by the ways count.
        Appended to win_data as a distinct win so it flows through recording/emission like any other,
        and stacks on top of the symbol wins those wilds complete. Mirrors evaluateWildPay in ways.ts.

        No-op unless every reel carries a wild. All wild cells are listed as positions so they are
        removed by the tumble (they participated in the win)."""
        wild = self.config.special_symbols["wild"][0]
        per_reel_cells = []
        for reel in range(self.config.num_reels):
            cells = [
                {"reel": reel, "row": row}
                for row in range(len(self.board[reel]))
                if self.board[reel][row].name == wild
            ]
            if not cells:
                return  # wild missing on a reel → no flat wild pay
            per_reel_cells.append(cells)

        positions = [c for cells in per_reel_cells for c in cells]
        base = self.config.wild_pay
        win = round(base * self.global_multiplier, 2)
        self.win_data["wins"].append(
            {
                "symbol": wild,
                "kind": self.config.num_reels,
                "win": win,
                "positions": positions,
                "meta": {
                    "ways": 1,
                    "globalMult": self.global_multiplier,
                    "winWithoutMult": base,
                    "symbolMult": 0,
                    "wildPay": True,
                },
            }
        )
        self.win_data["totalWin"] = round(self.win_data["totalWin"] + win, 2)
