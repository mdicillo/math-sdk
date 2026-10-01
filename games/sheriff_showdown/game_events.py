"""Sheriff Showdown book events, exactly as the math spec's section 14.5 defines them (the client's
src/rgs/sheriff/book.ts; `frontend_contract` in math_spec.json). These replace the SDK's standard events.

Money fields are book units: 100 = 1.00x the base bet (`to_units`). Multiples of the bet (`basePay`, `multiplier`,
`awardX`) are written as they are.
"""


from spec import SHERIFF_VALUE


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


def showdown_event(gamestate, sd: dict, paid: int) -> None:
    """Instead of reveal + winInfo on a Showdown spin. `paid` (book units) is the award as paid, clamped at the max
    win; `awardX` is the drawn award x bet."""
    event = {
        "type": "showdown",
        "board": sd["board"],
        "gameType": gamestate.gametype,
        "modifier": sd["modifier"],
        "sheriffValue": SHERIFF_VALUE,
    }
    if "challenger" in sd:
        event["challenger"] = sd["challenger"]
        event["winner"] = sd["winner"]
    if "number" in sd:
        event["number"] = sd["number"]
    event["awardX"] = sd["awardX"]
    event["amount"] = paid
    add_event(gamestate, event)


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


def bonus_trigger_event(gamestate, scatter: dict, mode: dict) -> None:
    """Natural trigger only (3/4/5 scatters on a base or ante reel spin); never on a buy."""
    add_event(
        gamestate,
        {"type": "bonusTrigger", "count": scatter["count"], "positions": scatter["positions"], "level": mode["level"], "mode": mode["id"]},
    )


def bonus_start_event(gamestate, mode: dict) -> None:
    """Start of every free-spins round (natural: after bonusTrigger; buy: the book's first event)."""
    add_event(
        gamestate,
        {
            "type": "bonusStart",
            "level": mode["level"],
            "mode": mode["id"],
            "spins": mode["spins"],
            "wildFloor": mode["wild_floor"],
            "guarantees": {"showdowns": mode["min_showdowns"], "sharpshooter": mode["needs_sharpshooter"]},
            "source": mode["source"],
        },
    )


def bonus_retrigger_event(gamestate, added: int, awarded: int, remaining: int, capped: bool) -> None:
    add_event(gamestate, {"type": "bonusRetrigger", "added": added, "awarded": awarded, "remaining": remaining, "capped": capped})


def bonus_update_event(gamestate, remaining: int, awarded: int, total_win: int) -> None:
    """After every free spin (reel spin or Showdown). `total_win`: the feature total so far, book units."""
    add_event(gamestate, {"type": "bonusUpdate", "remaining": remaining, "awarded": awarded, "totalWin": total_win})


def bonus_end_event(gamestate, mode: dict, total_win: int, max_win: bool) -> None:
    add_event(gamestate, {"type": "bonusEnd", "level": mode["level"], "totalWin": total_win, "maxWin": max_win})
