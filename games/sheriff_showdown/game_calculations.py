"""Sheriff Showdown rules as pure functions over a board (board[reel][row] symbol ids, rows 0-4) and its multipliers
(mults[reel][row], 0 = plain / not a wild). Amounts are x bet. A rule-for-rule port of the client's
src/rgs/sheriff/engine.ts (itself a port of the outline's engine.py); the names follow it.
"""

import random

from spec import (
    ANTICIPATION_HEAVY_SCATTERS,
    ANTICIPATION_MIN_SCATTERS,
    CLEAN_STOPS,
    PAYING_SYMBOLS,
    PAYLINES,
    PAYTABLE,
    REELS,
    ROWS,
    SCATTER,
    SCATTER_PAYS,
    SHARPSHOOTER_MULTIPLIERS,
    SHARPSHOOTER_PRESENT_MAX_WILDS,
    SHARPSHOOTER_PRESENT_PAIR_SAMPLE,
    SHARPSHOOTER_RATE,
    SHARPSHOOTER_WILD_COUNT,
    SHERIFF_VALUE,
    SHERIFF_WIN_CHANCE,
    CHALLENGERS,
    CHALLENGER_WEIGHTS,
    NUMBER_TABLES,
    STRIPS,
    WINCAP_X,
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


def natural_multipliers(board: list, floor: int, ladder: dict = None) -> list:
    """Multipliers on the naturally landed wilds (sections 5 / 7): the tier's wild floor in free spins, a draw from
    the WILD Ante ladder (raised to the floor), or 0 (plain)."""
    return [[(max(draw(ladder), floor) if ladder else floor) if sym == WILD else 0 for sym in col] for col in board]


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


def line_pays_plain(board: list, line: list) -> bool:
    """Does the payline start with a 3+ run of one paying symbol (W substitutes; all-W counts)?"""
    sym = None
    for reel in range(3):
        cell = board[reel][line[reel]]
        if cell == WILD:
            continue
        if cell == SCATTER or cell not in PAYTABLE:
            return False
        if sym is None:
            sym = cell
        elif cell != sym:
            return False
    return True


# --- Sharpshooter (section 6; formerly Deputized) ---------------------------------------------------------------


def sharpshooter(landed: list, landed_mults: list, floor: int, present: bool = True, content: dict = None) -> dict:
    """Sharpshooter (section 6). Steps 1-5 decide the award: convert cells to multiplier wilds - the first wild (or
    the two fallback cells) guarantees a line win, the rest land on random free cells; any cell can take one. Step 6
    then rebuilds the wilds shown to display exactly that award with more wilds when it can (present_sharpshooter);
    the award never changes.

    `content`: a bet mode's own Sharpshooter (SHARPSHOOTER Ante, section 7) - its wild counts and multipliers, and with
    `in_run` every wild after the guaranteed one placed inside a winning run and no step 6 (the award's board is
    shown)."""
    mult_table = content["multipliers"] if content else SHARPSHOOTER_MULTIPLIERS
    board = [list(col) for col in landed]
    mults = [list(col) for col in landed_mults]
    taken = [[False] * ROWS for _ in range(REELS)]
    wilds = []

    def place(reel, row, multiplier=None):
        if multiplier is None:
            multiplier = max(draw(mult_table), floor)
        wilds.append({"reel": reel, "row": row, "from": landed[reel][row], "multiplier": multiplier})
        board[reel][row] = WILD
        mults[reel][row] = multiplier
        taken[reel][row] = True

    k = draw(content["wild_count"] if content else SHARPSHOOTER_WILD_COUNT)

    # 1) Guaranteed win: a cell on reels 1-3 whose conversion to W makes a line through that cell pay. Tested against
    #    the landed board (nothing is placed yet).
    candidates = []
    for reel in range(3):
        for row in range(ROWS):
            through = [line for line in PAYLINES if line[reel] == row]
            if not through:
                continue
            prev = board[reel][row]
            board[reel][row] = WILD
            pays = any(line_pays_plain(board, line) for line in through)
            board[reel][row] = prev
            if pays:
                candidates.append((reel, row))
    fallback = False
    if candidates:
        place(*random.choice(candidates))
    else:
        # Fallback: the reel 1 and reel 2 cells of a random line, skipping cells already W or showing its reel 3
        # symbol, so that symbol pays at least 3 of a kind.
        fallback = True
        line = PAYLINES[random.randrange(len(PAYLINES))]
        s3 = landed[2][line[2]]
        for reel in (0, 1):
            row = line[reel]
            sym = landed[reel][row]
            if sym != s3 and sym != WILD:
                place(reel, row)
    guaranteed_cells = [{"reel": w["reel"], "row": w["row"]} for w in wilds]

    if content and content["in_run"]:
        # 3) SHARPSHOOTER Ante: each further wild draws its multiplier, then lands on a random cell not showing W such
        #    that every Sharpshooter wild on the board (the new one included) lies inside a winning run; none: stop.
        #    Its board is the one shown (no step 6).
        while len(wilds) < k:
            multiplier = max(draw(mult_table), floor)
            cells = []
            for reel in range(REELS):
                for row in range(ROWS):
                    if board[reel][row] == WILD:
                        continue
                    prev_sym, prev_mult = board[reel][row], mults[reel][row]
                    board[reel][row] = WILD
                    mults[reel][row] = multiplier
                    if all_in_runs(board, mults, wilds + [{"reel": reel, "row": row}]):
                        cells.append((reel, row))
                    board[reel][row] = prev_sym
                    mults[reel][row] = prev_mult
            if not cells:
                break
            reel, row = random.choice(cells)
            place(reel, row, multiplier)
        return {"wilds": wilds, "guaranteed": {"cells": guaranteed_cells, "fallback": fallback}, "board": board, "multipliers": mults}

    # 2) Remaining wilds on random free cells, uniformly without replacement.
    remaining = max(k - len(wilds), 0)
    if remaining > 0:
        free = [(reel, row) for reel in range(REELS) for row in range(ROWS) if not taken[reel][row]]
        while remaining > 0 and free:
            i = random.randrange(len(free))
            cell = free[i]
            free[i] = free[-1]
            free.pop()
            place(*cell)
            remaining -= 1

    # 6) Presentation: show the same award with more wilds, every one inside a winning run.
    award = sum(line["payX"] for line in evaluate_lines(board, mults))
    shown = present_sharpshooter(landed, landed_mults, award, floor, len(wilds)) if present else None
    if shown:
        return shown
    return {"wilds": wilds, "guaranteed": {"cells": guaranteed_cells, "fallback": fallback}, "board": board, "multipliers": mults}


def all_in_runs(board: list, mults: list, cells: list) -> bool:
    """Does every one of `cells` lie inside the run of a paying line's best result (evaluate_lines)?"""
    in_run = {(p["reel"], p["row"]) for line in evaluate_lines(board, mults) for p in line["positions"]}
    return all((c["reel"], c["row"]) in in_run for c in cells)


# --- Sharpshooter presentation (section 6 step 6; reference engine.sharpshooter_presentation) -------------------
# Cells are flat indices reel * ROWS + row; a set of cells is a 25-bit mask.

LINE_CELLS = [[reel * ROWS + row for reel, row in enumerate(line)] for line in PAYLINES]
# Best pay of any symbol for a run of n (an all-wild prefix of n can stand for any symbol).
BEST_PAY_AT = [max(PAYTABLE[s].get(n, 0) for s in PAYING_SYMBOLS) for n in range(REELS + 1)]


def bit_count(mask: int) -> int:
    return bin(mask).count("1")


def mask_cells(mask: int) -> list:
    return [c for c in range(REELS * ROWS) if mask & (1 << c)]


def lines_flat(syms: list, mults: list) -> tuple:
    """Per paying line of a flat board: base pay and run cells of the best result (evaluate_lines semantics: only the
    first non-wild symbol X can run past the leading wilds, so the best is X's run, or any symbol's run over the j
    leading wilds alone). Returns (total, [(pay, run cells)])."""
    total, lines = 0, []
    for cells in LINE_CELLS:
        j, wild_sum = 0, 0
        while j < REELS and syms[cells[j]] == WILD:
            wild_sum += mults[cells[j]]
            j += 1
        best_v, best_pay, best_n = 0, 0, 0
        if j >= 3:
            best_pay, best_n = BEST_PAY_AT[j], j
            best_v = best_pay * (wild_sum if wild_sum > 0 else 1)
        if j < REELS:
            x = syms[cells[j]]
            pays = PAYTABLE.get(x)
            if pays:
                n, msum = j, wild_sum
                while n < REELS and (syms[cells[n]] == x or syms[cells[n]] == WILD):
                    msum += mults[cells[n]]
                    n += 1
                pay = pays.get(n, 0)
                v = pay * (msum if msum > 0 else 1)
                if pay > 0 and v > best_v:
                    best_v, best_pay, best_n = v, pay, n
        if best_v > 0:
            total += best_v
            lines.append((best_pay, cells[:best_n]))
    return total, lines


def present_candidates(syms: list, kmax: int) -> list:
    """Candidate wild sets (masks): one line's run built by converting its mismatches, optionally its matching cells
    too, plus unions of two from a random sample."""
    out = set()
    for cells in LINE_CELLS:
        for sym in PAYING_SYMBOLS:
            pays = PAYTABLE[sym]
            for n in range(3, REELS + 1):
                if not pays.get(n, 0) > 0:
                    continue
                need, pad = 0, []
                for c in cells[:n]:
                    if syms[c] != sym and syms[c] != WILD:
                        need |= 1 << c
                    elif syms[c] == sym:
                        pad.append(c)
                if bit_count(need) > kmax:
                    continue
                for sub in range(1 << len(pad)):
                    mask = need
                    for i, c in enumerate(pad):
                        if sub & (1 << i):
                            mask |= 1 << c
                    if 1 <= bit_count(mask) <= kmax:
                        out.add(mask)
    sample = sorted(out)
    random.shuffle(sample)
    sample = sample[:SHARPSHOOTER_PRESENT_PAIR_SAMPLE]
    for i in range(len(sample)):
        for j in range(i + 1, len(sample)):
            u = sample[i] | sample[j]
            if bit_count(u) <= kmax:
                out.add(u)
    return list(out)


def solve_mults(coef: list, target: float, vals: list) -> list:
    """Every multiplier tuple (values from `vals`, ascending) with sum(coef[i] * m[i]) == target."""
    order = sorted(range(len(coef)), key=lambda i: -coef[i])
    sols = []
    acc = [0] * len(coef)

    def rec(i, rem):
        if i == len(order):
            if abs(rem) < 1e-9:
                sols.append(list(acc))
            return
        c = coef[order[i]]
        rest_min = sum(coef[order[j]] for j in range(i + 1, len(order))) * vals[0]
        for v in vals:
            left = rem - c * v
            if left < rest_min - 1e-9:
                break
            acc[order[i]] = v
            rec(i + 1, left)

    rec(0, target)
    return sols


def present_sharpshooter(landed: list, landed_mults: list, award: float, floor: int, n_award: int):
    """Rebuild a Sharpshooter spin's wilds to show exactly `award` with the most wilds (up to the spec's max): every
    new wild inside a winning run, multipliers from the Sharpshooter table raised to `floor`, landed wilds keeping
    theirs. None unless it shows more than `n_award` wilds (then the award step's wilds stay)."""
    syms0 = [landed[reel][row] for reel in range(REELS) for row in range(ROWS)]
    mults0 = [landed_mults[reel][row] for reel in range(REELS) for row in range(ROWS)]
    vals = sorted({max(v, floor) for v in SHARPSHOOTER_MULTIPLIERS})
    by_k = {}
    for mask in present_candidates(syms0, SHARPSHOOTER_PRESENT_MAX_WILDS):
        k = bit_count(mask)
        if k > n_award:
            by_k.setdefault(k, []).append(mask)
    for k in sorted(by_k, reverse=True):
        masks = by_k[k]
        random.shuffle(masks)
        for mask in masks:
            cells = mask_cells(mask)
            syms = list(syms0)
            m0 = list(mults0)
            for c in cells:
                syms[c] = WILD
                m0[c] = 0
            konst = 0
            coef = [0] * k
            for pay, run in lines_flat(syms, m0)[1]:
                fixed, hit = 0, False
                for c in run:
                    fixed += m0[c]
                    if c in cells:
                        coef[cells.index(c)] += pay
                        hit = True
                konst += pay * fixed if hit else pay * (fixed if fixed > 0 else 1)
            if any(c == 0 for c in coef):
                continue  # a wild outside every winning run
            sols = solve_mults(coef, award - konst, vals)
            random.shuffle(sols)
            for m in sols:
                mults = list(m0)
                for c, v in zip(cells, m):
                    mults[c] = v
                if abs(lines_flat(syms, mults)[0] - award) > 1e-9:
                    continue
                wilds = [{"reel": c // ROWS, "row": c % ROWS, "from": syms0[c], "multiplier": v} for c, v in zip(cells, m)]
                board = [list(col) for col in landed]
                multipliers = [list(col) for col in landed_mults]
                for w in wilds:
                    board[w["reel"]][w["row"]] = WILD
                    multipliers[w["reel"]][w["row"]] = w["multiplier"]
                return {
                    "wilds": wilds,
                    "guaranteed": {"cells": [{"reel": w["reel"], "row": w["row"]} for w in wilds], "fallback": False},
                    "board": board,
                    "multipliers": multipliers,
                }
    return None


# --- Showdown (section 8) ----------------------------------------------------------------------------------------

CENTER_ROW = 2


def showdown_board(modifier: str, right_id: str) -> list:
    """The Showdown board (section 14.2): the Sheriff on reels 1-2, blanks on reel 3 with the modifier in the center,
    the challenger or number on reels 4-5."""
    sheriff = ["SHERIFF"] * ROWS
    mid = [modifier if row == CENTER_ROW else "BLANK" for row in range(ROWS)]
    right = [right_id] * ROWS
    return [sheriff, list(sheriff), mid, right, list(right)]


def draw_showdown(ctx: dict) -> dict:
    """Draw a Showdown outcome from `ctx`'s odds: the modifier, then VS a challenger and who wins (the Sheriff with
    SHERIFF_WIN_CHANCE: 10 + the challenger's value, else the challenger's value), or a number from the modifier's table
    (+: 10 + number, X: 10 x number). The award is capped at the max win."""
    tables = NUMBER_TABLES[ctx["table"]]
    modifier = draw(ctx["modifiers"])
    if modifier == "VS":
        challenger = draw(CHALLENGER_WEIGHTS)
        value = CHALLENGERS[challenger]
        sheriff_wins = random.random() < SHERIFF_WIN_CHANCE
        award_x = SHERIFF_VALUE + value if sheriff_wins else value
        return {
            "modifier": modifier,
            "challenger": {"id": challenger, "value": value},
            "winner": "sheriff" if sheriff_wins else "challenger",
            "awardX": min(award_x, int(WINCAP_X)),
            "board": showdown_board(modifier, challenger),
        }
    number = draw(tables[modifier])
    award_x = SHERIFF_VALUE + number if modifier == "PLUS" else SHERIFF_VALUE * number
    return {"modifier": modifier, "number": number, "awardX": min(award_x, int(WINCAP_X)), "board": showdown_board(modifier, f"N{number}")}


# --- One normal reel spin (sections 2, 4-7) ---------------------------------------------------------------------


def play_reel_spin(strip_id: str, floor: int = 0, ladder: dict = None, sharp: dict = None, force_sharp: bool = None) -> dict:
    """One normal reel spin: the Sharpshooter trigger first (its chance for the strip set, or `sharp`'s own), then the
    stops (every reel scatter-free on a Sharpshooter spin), then the landed wilds' multipliers and the Sharpshooter
    itself. `force_sharp` pins whether it's a Sharpshooter spin (books whose criteria call for one)."""
    rate = sharp["rate"] if sharp else SHARPSHOOTER_RATE[strip_id]
    is_sharp = (random.random() < rate) if force_sharp is None else force_sharp
    spin = spin_reels(STRIPS[strip_id], CLEAN_STOPS[strip_id], is_sharp)
    mults = natural_multipliers(spin["board"], floor, ladder)
    shot = sharpshooter(spin["board"], mults, floor, True, sharp) if is_sharp else None
    lines = evaluate_lines(shot["board"] if shot else spin["board"], shot["multipliers"] if shot else mults)
    scatter = scatter_result(spin["board"])
    win_x = scatter["payX"] + sum(line["payX"] for line in lines)
    return {
        "strips": strip_id,
        "spin": spin,
        "multipliers": mults,
        "anticipation": anticipation_levels(spin["board"]),
        "sharpshooter": shot,
        "lines": lines,
        "scatter": scatter,
        "winX": win_x,
    }


def play_spin(ctx: dict, strip_id: str, floor: int = 0, ladder: dict = None, sharp: dict = None) -> dict:
    """A paid spin (base / antes) or a free spin: a Showdown with the context's chance, else a normal reel spin."""
    if random.random() < ctx["rate"]:
        showdown = draw_showdown(ctx)
        return {"kind": "showdown", "showdown": showdown, "winX": showdown["awardX"]}
    return {"kind": "reels", **play_reel_spin(strip_id, floor, ladder, sharp)}
