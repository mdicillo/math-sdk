from src.events.events import *


def padded(gamestate, cell: dict) -> dict:
    """A board position as the SDK's events write it: rows start at 1 when padding symbols are included."""
    return {"reel": cell["reel"], "row": cell["row"] + (1 if gamestate.config.include_padding else 0)}


def wild_frame_event(gamestate):
    """WILD STRIKE's wandering frame for this spin: the cell it settles on, and every WILD that beams (the frame copies
    onto each). `beams` is empty when no WILD landed in the frame."""
    event = {
        "index": len(gamestate.book.events),
        "type": "wildFrame",
        "cell": padded(gamestate, gamestate.frame_cell),
        "beams": [padded(gamestate, cell) for cell in gamestate.beams],
    }
    gamestate.book.add_event(event)


def wild_strike_event(gamestate):
    """WILD STRIKE's new wilds, each with its multiplier, struck onto the board before the wins evaluate."""
    event = {
        "index": len(gamestate.book.events),
        "type": "wildStrike",
        "wilds": [{**padded(gamestate, wild), "mult": wild["mult"]} for wild in gamestate.strike_wilds],
    }
    gamestate.book.add_event(event)
