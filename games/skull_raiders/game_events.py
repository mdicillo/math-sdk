"""Custom book events for the raid wheel.

The wheel is a base-game center-screen EVENT (not a board symbol): on a wheel round the normal line
evaluation is replaced by ATTACK (redraw whole paylines) or STEAL (sweep every 3+ group). These events
are informational for the client; the RTP-bearing win flows through the standard win-accounting events
(winInfo / setWin / setTotalWin / finalWin), so the analysis/verification still computes payoutMultiplier
correctly. Board positions are padding-adjusted (+1 row) to match the SDK reveal event.
"""

WHEEL_SPIN = "wheelSpin"
WHEEL_CONVERT = "wheelConvert"
WHEEL_STEAL = "wheelSteal"


def _pad_row(gamestate, row: int) -> int:
    """Shift a board row into the padded coordinate space the client renders (matches reveal_event)."""
    return row + 1 if gamestate.config.include_padding else row


def wheel_spin_event(gamestate, mode: str) -> None:
    """The wheel fired; `mode` is 'attack' or 'steal'."""
    gamestate.book.add_event(
        {"index": len(gamestate.book.events), "type": WHEEL_SPIN, "mode": mode}
    )


def wheel_convert_event(gamestate, cells: list) -> None:
    """ATTACK: the cells the fireballs redrew. Each cell = {reel, row, name, multiplier?}."""
    out = []
    for c in cells:
        cell = {"reel": c["reel"], "row": _pad_row(gamestate, c["row"]), "name": c["name"]}
        if c.get("multiplier", 1) > 1:
            cell["multiplier"] = int(c["multiplier"])
        out.append(cell)
    gamestate.book.add_event(
        {"index": len(gamestate.book.events), "type": WHEEL_CONVERT, "cells": out}
    )


def wheel_steal_event(gamestate, symbol: str, positions: list, total: float, multiplier: int, wins: list) -> None:
    """STEAL: the swept groups. `positions` are the present-symbol cells; `multiplier` is the summed
    wild factor; `wins` mirrors the per-group breakdown (symbol, kind, win)."""
    gamestate.book.add_event(
        {
            "index": len(gamestate.book.events),
            "type": WHEEL_STEAL,
            "symbol": symbol,
            "positions": [{"reel": p["reel"], "row": _pad_row(gamestate, p["row"])} for p in positions],
            "total": int(round(total * 100, 0)),
            "multiplier": int(multiplier),
            "wins": wins,
        }
    )
