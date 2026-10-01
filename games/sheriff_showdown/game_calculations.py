"""Sheriff Showdown rules as pure functions over a board (board[reel][row] symbol ids, rows 0-4) and its multipliers
(mults[reel][row], 0 = plain / not a wild). Amounts are x bet. A rule-for-rule port of the client's
src/rgs/sheriff/engine.ts (itself a port of the outline's engine.py); the names follow it.
"""

import random

from spec import (
    ANTICIPATION_HEAVY_SCATTERS,
    ANTICIPATION_MIN_SCATTERS,
    PAYING_SYMBOLS,
    PAYLINES,
    PAYTABLE,
    REELS,
    ROWS,
    SCATTER,
    SCATTER_PAYS,
    WILD,
)


def draw(table: dict):
    """One value from a weighted table {value: weight}."""
    total = sum(table.values())
    roll = random.random() * total
    for value, weight in table.items():
        roll -= weight
        if roll < 0:
            return value
    return value


# --- Reel spin (section 2) --------------------------------------------------------------------------------------


def read_stops(strips: list, stops: list) -> dict:
    """The window and the off-screen symbols one position above (stop - 1) and below (stop + 5) each reel's window."""
    board, above, below = [], [], []
    for reel in range(REELS):
        strip, stop = strips[reel], stops[reel]
        length = len(strip)
        board.append([strip[(stop + row) % length] for row in range(ROWS)])
        above.append(strip[(stop - 1) % length])
        below.append(strip[(stop + ROWS) % length])
    return {"stops": list(stops), "board": board, "padding": {"above": above, "below": below}}


def spin_reels(strips: list, clean: list, sharp: bool = False) -> dict:
    """Every reel's stop drawn uniformly: from its scatter-free stops on a Sharpshooter spin (`sharp`), else from all."""
    stops = [random.choice(clean[reel]) if sharp else random.randrange(len(strips[reel])) for reel in range(REELS)]
    return read_stops(strips, stops)


# --- Line evaluation (section 4) --------------------------------------------------------------------------------


def evaluate_lines(board: list, mults: list) -> list:
    """Best result on each payline; only paying lines are returned. Per line, every paying symbol's run from reel 1
    (W substitutes) pays paytable x the sum of the wild multipliers in the run (1 if that sum is 0); the line pays its
    best symbol, ties going to the first symbol in paytable order."""
    out = []
    for line_id, line in enumerate(PAYLINES):
        best = None
        for sym in PAYING_SYMBOLS:
            count, msum = 0, 0
            while count < REELS:
                cell = board[count][line[count]]
                if cell != sym and cell != WILD:
                    break
                msum += mults[count][line[count]]
                count += 1
            base_pay = PAYTABLE[sym].get(count, 0)
            if base_pay <= 0:
                continue
            multiplier = msum if msum > 0 else 1
            pay_x = base_pay * multiplier
            if best is None or pay_x > best["payX"]:
                best = {
                    "lineId": line_id,
                    "symbol": sym,
                    "count": count,
                    "positions": [{"reel": reel, "row": line[reel]} for reel in range(count)],
                    "basePay": base_pay,
                    "multiplier": multiplier,
                    "payX": pay_x,
                }
        if best is not None:
            out.append(best)
    return out


def scatter_result(board: list) -> dict:
    """Scatters anywhere: count, cells, and the pay (the top count pays for that many or more)."""
    positions = [{"reel": reel, "row": row} for reel in range(REELS) for row in range(ROWS) if board[reel][row] == SCATTER]
    count = len(positions)
    pay_x = SCATTER_PAYS.get(min(count, max(SCATTER_PAYS)), 0)
    return {"count": count, "positions": positions, "payX": pay_x}


# --- Anticipation (section 13) ----------------------------------------------------------------------------------


def anticipation_levels(board: list) -> list:
    """Per reel: 0 none, 1 light, 2 heavy, from the final board. Every reel after the 2nd scatter anticipates: heavy
    with at least 3 scatters on the reels to the left, light with 2."""
    out, left = [], 0
    for reel in range(REELS):
        heavy = left >= ANTICIPATION_HEAVY_SCATTERS
        light = not heavy and left >= ANTICIPATION_MIN_SCATTERS
        out.append(2 if heavy else 1 if light else 0)
        if SCATTER in board[reel]:
            left += 1
    return out


# --- One normal reel spin (sections 2, 4-7) ---------------------------------------------------------------------


def play_reel_spin(strip_id: str, strips: list, clean: list) -> dict:
    """One normal reel spin. Step 1: the stops and the line and scatter pays only (no wild multipliers, no
    Sharpshooter)."""
    spin = spin_reels(strips, clean)
    mults = [[0] * ROWS for _ in range(REELS)]
    lines = evaluate_lines(spin["board"], mults)
    scatter = scatter_result(spin["board"])
    win_x = scatter["payX"] + sum(line["payX"] for line in lines)
    return {
        "strips": strip_id,
        "spin": spin,
        "multipliers": mults,
        "anticipation": anticipation_levels(spin["board"]),
        "lines": lines,
        "scatter": scatter,
        "winX": win_x,
    }
