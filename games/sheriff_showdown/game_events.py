"""Sheriff Showdown book events, exactly as the math spec's section 14.5 defines them (the client's
src/rgs/sheriff/book.ts; `frontend_contract` in math_spec.json). These replace the SDK's standard events.

Money fields are book units: 100 = 1.00x the base bet (`to_units`). Multiples of the bet (`basePay`, `multiplier`,
`awardX`) are written as they are.
"""


def to_units(x: float) -> int:
    """x base bet -> book units (100 = 1.00x). Every pay in this game is a multiple of 0.5x, so this is exact."""
    units = round(x * 100)
    assert abs(units - x * 100) < 1e-6, f"not a whole book unit: {x}"
    return units


def add_event(gamestate, event: dict) -> None:
    gamestate.book.add_event({"index": len(gamestate.book.events), **event})


def reveal_event(gamestate, result: dict) -> None:
    """Every normal reel spin: the board as landed, its multipliers, the off-screen symbols, stops, strip set and the
    math-owned anticipation per reel."""
    spin = result["spin"]
    add_event(
        gamestate,
        {
            "type": "reveal",
            "board": spin["board"],
            "multipliers": result["multipliers"],
            "padding": spin["padding"],
            "stops": spin["stops"],
            "strips": result["strips"],
            "anticipation": result["anticipation"],
            "gameType": gamestate.gametype,
        },
    )


def sharpshooter_event(gamestate, shot: dict) -> None:
    """After reveal, before winInfo, when the Sharpshooter triggers: the wilds shown (each with the symbol it replaced
    and its multiplier), the guaranteed cells, and the board and multipliers after conversion."""
    add_event(
        gamestate,
        {
            "type": "sharpshooter",
            "wilds": shot["wilds"],
            "guaranteed": shot["guaranteed"],
            "board": shot["board"],
            "multipliers": shot["multipliers"],
        },
    )


def win_info_event(gamestate, result: dict, paid: int) -> None:
    """After every normal reel spin, even with no win. `paid` (book units) is what the spin added to the round."""
    wins = [
        {
            "lineId": line["lineId"],
            "symbol": line["symbol"],
            "count": line["count"],
            "positions": line["positions"],
            "basePay": line["basePay"],
            "multiplier": line["multiplier"],
            "amount": to_units(line["payX"]),
        }
        for line in result["lines"]
    ]
    event = {"type": "winInfo", "wins": wins}
    scatter = result["scatter"]
    if scatter["payX"] > 0:
        event["scatter"] = {"count": scatter["count"], "positions": scatter["positions"], "amount": to_units(scatter["payX"])}
    event["total"] = paid
    add_event(gamestate, event)


def set_total_win_event(gamestate, amount: int) -> None:
    add_event(gamestate, {"type": "setTotalWin", "amount": amount})


def final_win_event(gamestate, amount: int, max_win: bool) -> None:
    add_event(gamestate, {"type": "finalWin", "amount": amount, "maxWin": max_win})
