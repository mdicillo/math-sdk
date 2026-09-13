import random
from game_calculations import GameCalculations
from game_events import wild_frame_event, wild_strike_event
from src.calculations.lines import Lines


class GameExecutables(GameCalculations):

    def evaluate_lines_board(self):
        """Populate win-data, record wins, transmit events."""
        self.win_data = Lines.get_lines(self.board, self.config, global_multiplier=self.global_multiplier)
        Lines.record_lines_wins(self)
        self.win_manager.update_spinwin(self.win_data["totalWin"])
        Lines.emit_linewin_events(self)

    def place_wild_frame(self, tuning: dict, on_wild: bool = False) -> None:
        """WILD STRIKE's frame, settled before the reels stop: on a landed WILD when `on_wild` (a feature's guaranteed
        strike) or with the tuning's frame_on_wild chance, then every landed WILD beams; otherwise on a cell without a
        WILD (on a board of nothing but WILDs it can only settle on one)."""
        wilds, others = [], []
        for reel in range(self.config.num_reels):
            for row in range(self.config.num_rows[reel]):
                (wilds if self.board[reel][row].check_attribute("wild") else others).append({"reel": reel, "row": row})
        on_wild = on_wild or random.random() < tuning["frame_on_wild"]
        if wilds and (on_wild or not others):
            self.frame_cell, self.beams = random.choice(wilds), wilds
        else:
            self.frame_cell, self.beams = random.choice(others), []
        wild_frame_event(self)

    def run_wild_strike(self, tuning: dict, certain: bool = False) -> None:
        """WILD STRIKE: only when WILDs beam, likelier the more beam (certain for a feature's guaranteed strike), aimed to
        pay between the floor and the ceiling. The new wilds go onto the board before the lines evaluate."""
        self.strike_wilds = []
        if not self.beams:
            return
        chances = tuning["chance_by_beams"]
        if not certain and random.random() >= chances[min(len(self.beams), len(chances)) - 1]:
            return
        wilds = self.plan_strike(tuning)
        if not wilds:
            return
        for wild in wilds:
            self.board[wild["reel"]][wild["row"]] = self.strike_wild(wild["mult"])
        self.get_special_symbols_on_board()
        self.strike_wilds = wilds
        self.record({"wild_strike": self.gametype, "wilds": len(wilds)})
        wild_strike_event(self)
