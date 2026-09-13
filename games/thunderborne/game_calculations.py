import random
from src.executables.executables import Executables
from src.calculations.lines import Lines
from src.calculations.statistics import get_random_outcome
from game_config import FULL_BOARD


class GameCalculations(Executables):
    """WILD STRIKE's aim (rebuild provider.ts planStrike / aimStrike): where the new wilds go and what they pay."""

    def open_cells(self) -> list:
        """Cells holding neither a WILD nor a BONUS symbol, reel by reel."""
        return [
            {"reel": reel, "row": row}
            for reel in range(self.config.num_reels)
            for row in range(self.config.num_rows[reel])
            if not self.board[reel][row].check_attribute("wild", "scatter")
        ]

    def strike_wild(self, mult: int):
        """A new WILD STRIKE wild carrying `mult`."""
        wild = self.create_symbol("W")
        wild.assign_attribute({"multiplier": mult})
        return wild

    def strike_pay(self, wilds: list) -> float:
        """What the board pays (× base bet) once `wilds` are struck onto it."""
        board = [column[:] for column in self.board]
        for wild in wilds:
            board[wild["reel"]][wild["row"]] = self.strike_wild(wild["mult"])
        return Lines.get_lines(board, self.config)["totalWin"]

    def aim_strike(self, open_cells: list, mults: list, tuning: dict):
        """Place wilds carrying `mults` on `open_cells` so the spin pays between the tuning's floor and ceiling: random
        placements first (one of the good ones, leaning by aim_lean), then wild by wild on the cell that pays most.
        "low" / "high" when neither lands in range — mostly under the floor, or over the ceiling."""
        floor, ceiling = tuning["floor"], tuning["ceiling"]
        good, weights, high = [], [], 0
        for _ in range(tuning["aim_tries"]):
            cells = random.sample(open_cells, len(mults))
            wilds = [{"reel": cell["reel"], "row": cell["row"], "mult": mult} for cell, mult in zip(cells, mults)]
            pay = self.strike_pay(wilds)
            if floor <= pay <= ceiling:
                good.append(wilds)
                weights.append(pay ** -tuning["aim_lean"])
            elif pay > ceiling:
                high += 1
        if good:
            return random.choices(good, weights)[0]

        placed, free = [], list(open_cells)
        for mult in mults:
            best, best_pay = -1, -1
            for idx, cell in enumerate(free):
                pay = self.strike_pay(placed + [{"reel": cell["reel"], "row": cell["row"], "mult": mult}])
                if pay <= ceiling and pay > best_pay:
                    best, best_pay = idx, pay
            if best < 0:
                break
            cell = free.pop(best)
            placed.append({"reel": cell["reel"], "row": cell["row"], "mult": mult})
        if len(placed) == len(mults) and floor <= self.strike_pay(placed) <= ceiling:
            return placed
        return "high" if high > tuning["aim_tries"] / 2 else "low"

    def plan_strike(self, tuning: dict):
        """Roll a strike's size and multipliers and aim it so the spin pays between the floor and the ceiling, a wild
        more or fewer at a time when it can't. The new wilds, or None if no strike fits."""
        open_cells = self.open_cells()
        if not open_cells:
            return None
        low, high = get_random_outcome(tuning["sizes"])
        size = len(open_cells) if low == FULL_BOARD else min(len(open_cells), random.randint(low, high))
        for _ in range(tuning["resizes"] + 1):
            mults = [get_random_outcome(tuning["multipliers"]) for _ in range(size)]
            aimed = self.aim_strike(open_cells, mults, tuning)
            if isinstance(aimed, list):
                return aimed
            size = min(len(open_cells), size + 1) if aimed == "low" else max(1, size - 1)
        return None
