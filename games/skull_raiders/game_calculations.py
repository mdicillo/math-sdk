from src.executables.executables import Executables


class GameCalculations(Executables):
    """Game-specific pure calculations. Currently: the STEAL scorer for the raid wheel."""

    @staticmethod
    def evaluate_steal(board, config):
        """Score a STEAL board: sweep EVERY 3+ group present, ignore paylines, sum them, and multiply by
        the summed wild factor. Wilds are PURE MULTIPLIERS here — they do NOT pad symbol counts and are
        not themselves stealable (mirrors evaluateSteal in the TS model, evaluate.ts:138-214).

        Returns win_data in the same shape as Lines.get_lines: {"totalWin", "wins"} with RAW win amounts
        (multiples of total bet); the standard emitters scale by 100. Returns 0 wins if nothing reaches
        minMatch.
        """
        wild = config.special_symbols["wild"][0]
        cols = config.num_reels
        min_match = min(k for (k, _s) in config.paytable.keys())

        # Summed wild factor (only >=2 wilds contribute; floor at 1).
        wild_factor = 0
        for reel in range(len(board)):
            for cell in board[reel]:
                if cell.name == wild:
                    m = cell.get_attribute("multiplier") if cell.check_attribute("multiplier") else 1
                    if m > 1:
                        wild_factor += m
        wild_factor = max(wild_factor, 1)

        # Count and locate every non-wild symbol across the whole board.
        counts = {}
        positions = {}
        for reel in range(len(board)):
            for row in range(len(board[reel])):
                cell = board[reel][row]
                name = cell.name
                if name == wild:
                    continue
                counts[name] = counts.get(name, 0) + 1
                positions.setdefault(name, []).append({"reel": reel, "row": row})

        wins = []
        total = 0.0
        for name, count in counts.items():
            kind = min(count, cols)
            if count >= min_match and (kind, name) in config.paytable:
                pay = config.paytable[(kind, name)]
                win = round(pay * wild_factor, 2)
                total = round(total + win, 2)
                wins.append(
                    {
                        "symbol": name,
                        "kind": kind,
                        "win": win,
                        "positions": positions[name],
                        "meta": {"multiplier": int(wild_factor), "winWithoutMult": pay, "wheelSteal": True},
                    }
                )
        return {"totalWin": total, "wins": wins}
