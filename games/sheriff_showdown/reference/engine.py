"""
Sheriff Showdown - simulation engine.

Grid layout: grid[spin, reel, row], 5 reels x 5 rows. Center cell = reel 3, row 3 -> [2, 2].

Sharpshooter (2026-09-28; was Deputized): triggers at random on a normal reel spin with the context's chance
(C.SHARPSHOOTER_RATE); every cell can take a wild. Internal names still say `dep` for the feature flag.
"""
import itertools

import numpy as np

import config as C

SYM = {s: i for i, s in enumerate(C.SYMBOLS)}
W, S, H1 = SYM["W"], SYM["S"], SYM["H1"]
PAYING = [SYM[s] for s in C.PAYTABLE_DRAFT]          # 12 line-paying symbols
LINES = np.array(C.PAYLINES, dtype=np.int64)         # (20, 5)
REEL_IDX = np.arange(5)[None, :]                     # broadcast with LINES
CENTER_FLAT = 2 * 5 + 2                              # reel*5 + row


def line_wins_plain(g):
    """(N, 5, 5) boards -> (N, lines) bool: the line starts with a 3+ run of one paying symbol
    (W substitutes; an all-W start counts). Multipliers are irrelevant for win / no win."""
    f3 = g[:, REEL_IDX[:, :3], LINES[:, :3]]            # (N, lines, 3)
    nonw = f3 != W
    hi = np.where(nonw, f3, -1).max(2)
    lo = np.where(nonw, f3, 127).min(2)
    return (hi == -1) | ((hi == lo) & (hi != S))


# ---------------------------------------------------------------------------
# Reel strips
# ---------------------------------------------------------------------------
def build_strips(counts, rng):
    """Production strips: spread arrangement (see build_strips_spread)."""
    return build_strips_spread(counts, rng)


def build_strips_shuffled(counts, rng):
    """Random shuffle of non-scatter symbols (counts x STRIP_REPEAT), scatters placed evenly.
    Kept for comparison with the first-pass model."""
    strips = []
    for r in range(5):
        body = []
        for s, per_reel in counts.items():
            body += [SYM[s]] * (int(round(per_reel[r] * C.STRIP_REPEAT)))
        body = list(rng.permutation(body))
        groups = C.SCATTER_GROUPS[r]
        n_s = sum(len(g) for g in groups)
        length = len(body) + n_s
        anchors = [int(round(i * length / len(groups))) for i in range(len(groups))]
        pos = {a + o for a, g in zip(anchors, groups) for o in g}
        assert len(pos) == n_s and length / len(groups) >= 8, "scatter groups too dense"
        strip = [S if i in pos else body.pop() for i in range(length)]
        strips.append(np.array(strip, dtype=np.int8))
    return strips


def apply_swap(counts, swap):
    out = {k: list(v) for k, v in counts.items()}
    for s, delta in swap.items():
        out[s] = [a + b for a, b in zip(out[s], delta)]
        assert min(out[s]) >= 0
    return out


def paytable_array(pays):
    arr = np.zeros((len(C.SYMBOLS), 6))
    for s, (p3, p4, p5) in pays.items():
        arr[SYM[s], 3:6] = (p3, p4, p5)
    return arr


def _weights(d):
    k = np.array(list(d.keys()))
    w = np.array(list(d.values()), dtype=float)
    return k, w / w.sum()


DEP_N_VALS, DEP_N_P = _weights(C.SHARPSHOOTER_WILD_COUNT)
DEP_M_VALS, DEP_M_P = _weights(C.SHARPSHOOTER_MULTS)


def set_wild_count_weights(weights):
    """Swap the Sharpshooter wild-count weights (run_model solves them)."""
    global DEP_N_VALS, DEP_N_P
    DEP_N_VALS, DEP_N_P = _weights(weights)


# Flat cell indices (reel * 5 + row) of each payline, and a (lines * 5, 25) one-hot map from line
# positions to cells.
LINE_FLAT = np.arange(5)[None, :] * 5 + LINES
_LINE_ONEHOT = np.zeros((LINE_FLAT.size, 25), np.uint8)
_LINE_ONEHOT[np.arange(LINE_FLAT.size), LINE_FLAT.reshape(-1)] = 1


def in_run_mask(gf, mf, pay):
    """(n, 25) boards + multipliers -> (n, 25) bool: the cell lies inside the paying run of a line's best
    result (engine semantics: best symbol by pay x multiplier sum; ties go to the first symbol in
    PAYING order)."""
    n = gf.shape[0]
    Ls, Lm = gf[:, LINE_FLAT], mf[:, LINE_FLAT]          # (n, lines, 5)
    isw = Ls == W
    best = np.zeros(Ls.shape[:2])
    best_cnt = np.zeros(Ls.shape[:2], np.int64)
    for s in PAYING:
        run = np.logical_and.accumulate((Ls == s) | isw, axis=2)
        cnt = run.sum(2)
        p = pay[s][cnt]
        if not p.any():
            continue
        msum = (Lm * run).sum(2)
        v = p * np.where(msum > 0, msum, 1)
        upd = v > best
        best = np.where(upd, v, best)
        best_cnt = np.where(upd, cnt, best_cnt)
    pos_in = np.arange(5)[None, None, :] < best_cnt[:, :, None]
    return (pos_in.reshape(n, -1).astype(np.uint8) @ _LINE_ONEHOT) > 0


def place_in_run(sub_g, sub_m, sharp_cells, remaining, mults, floor, rng, pay):
    """SHARPSHOOTER BOOST step 3 (in place): add wilds one at a time. Each draws its multiplier, then lands
    on a random cell not showing W such that, afterwards, every Sharpshooter wild on the board (the new one
    included) lies inside a winning run. A spin with no such cell stops adding wilds."""
    vals, probs = mults
    remaining = remaining.copy()
    while True:
        idx = np.flatnonzero(remaining > 0)
        if idx.size == 0:
            return
        g0, m0, need0 = sub_g[idx], sub_m[idx], sharp_cells[idx]
        mdraw = np.maximum(rng.choice(vals, idx.size, p=probs), floor)
        valid = np.zeros((idx.size, 25), bool)
        for c in range(25):
            free = g0[:, c] != W
            if not free.any():
                continue
            g2, m2 = g0.copy(), m0.copy()
            g2[:, c] = W
            m2[:, c] = mdraw
            need = need0.copy()
            need[:, c] = True
            valid[:, c] = free & ~(need & ~in_run_mask(g2, m2, pay)).any(1)
        keys = np.where(valid, rng.random(valid.shape), np.inf)
        has = np.isfinite(keys.min(1))
        rows, cells = idx[has], keys[has].argmin(1)
        sub_g[rows, cells] = W
        sub_m[rows, cells] = mdraw[has]
        sharp_cells[rows, cells] = True
        remaining[rows] -= 1
        remaining[idx[~has]] = 0


# ---------------------------------------------------------------------------
# Reel spin
# ---------------------------------------------------------------------------
class ReelSpinner:
    def __init__(self, strips, pays, wild_mults=None, trigger_rate=None, sharp=None):
        """wild_mults: optional {multiplier: weight} for naturally landing wilds (WILD Ante).
        trigger_rate: the Sharpshooter chance per normal reel spin; None = the strips' H1-in-center chance
        (the old Deputized odds).
        sharp: optional Sharpshooter content for this mode (SHARPSHOOTER BOOST): {"counts": {k: weight},
        "mults": {multiplier: weight}, "in_run": bool}. in_run places every wild after the guaranteed one
        inside a winning run (place_in_run). None = the shared Sharpshooter weights, random placement."""
        self.wild_mults = _weights(wild_mults) if wild_mults else None
        self.sharp_counts = _weights(sharp["counts"]) if sharp else None
        self.sharp_mults = _weights(sharp["mults"]) if sharp else None
        self.sharp_in_run = bool(sharp and sharp.get("in_run"))
        self.strips = strips
        self.lens = np.array([len(s) for s in strips])
        self.pay = paytable_array(pays)
        self.scat_pay = np.zeros(11)
        for k, v in C.SCATTER_PAYS.items():
            self.scat_pay[k] = v
        top = max(C.SCATTER_PAYS)
        self.scat_pay[top:] = C.SCATTER_PAYS[top]          # 5+ scatters pay the 5 value
        # Sharpshooter / scatter exclusion: the trigger is drawn first; a Sharpshooter spin draws every
        # reel uniformly from its scatter-free stops, so it never shows a scatter (no symbol is overwritten).
        rows = np.arange(5)
        self.clean_stops = []
        for st in strips:
            win = st[(np.arange(len(st))[:, None] + rows) % len(st)]
            self.clean_stops.append(np.flatnonzero(~(win == S).any(1)))
        st3, L3 = strips[2], len(strips[2])
        # The strips' H1-in-center stops (the old Deputized trigger); only their share is used, as the
        # default trigger rate. The strips still keep H1 clear of scatters on reel 3.
        self.dep_stops = np.flatnonzero(st3[(np.arange(L3) + 2) % L3] == H1)
        assert np.isin(self.dep_stops, self.clean_stops[2]).all(), \
            "reel 3: a scatter is visible on a stop with H1 in the center"
        self.p_trig = len(self.dep_stops) / L3 if trigger_rate is None else trigger_rate

    def grids(self, n, rng, force_dep=None, return_stops=False):
        """Draw the Sharpshooter trigger (force_dep: bool mask of spins forced to trigger), then the stops.
        Returns (g, dep) or, with return_stops, (g, dep, stops)."""
        dep = rng.random(n) < self.p_trig
        if force_dep is not None:
            dep |= force_dep
        stops = [rng.integers(0, self.lens[r], n) for r in range(5)]
        if dep.any():
            for r in range(5):
                stops[r][dep] = rng.choice(self.clean_stops[r], dep.sum())
        g = np.empty((n, 5, 5), dtype=np.int8)
        rows = np.arange(5)
        for r in range(5):
            g[:, r, :] = self.strips[r][(stops[r][:, None] + rows) % self.lens[r]]
        return (g, dep, stops) if return_stops else (g, dep)

    def spin(self, n, rng, floor=0, force_dep=None, landed=False, final=False):
        """Returns line_win, scatter_count, sharpshooter_flag, sharpshooter_wild_count for n spins; with
        landed=True also the boards and multipliers as landed (before Sharpshooter); with final=True (and not
        landed) the final boards and multipliers instead."""
        g, dep = self.grids(n, rng, force_dep)
        mult = np.where(g == W, floor, 0).astype(np.int32)   # natural wilds: plain unless floor
        if self.wild_mults is not None:                       # WILD Ante: every wild has a multiplier
            nat = g == W
            vals, probs = self.wild_mults
            mult[nat] = np.maximum(rng.choice(vals, nat.sum(), p=probs), floor)

        g_landed, m_landed = (g.copy(), mult.copy()) if landed else (None, None)
        # --- Sharpshooter: converts cells to multiplier wilds. The first wild always completes a
        # paying line (guaranteed win); the rest land on random cells. Any cell can take a wild.
        gf, mf = g.reshape(n, 25), mult.reshape(n, 25)
        idx = np.flatnonzero(dep)
        n_dep_wilds = np.zeros(n, dtype=np.int16)
        if idx.size:
            m = idx.size
            sub_g, sub_m = gf[idx], mf[idx]
            n_vals, n_p = self.sharp_counts or (DEP_N_VALS, DEP_N_P)
            m_vals, m_p = self.sharp_mults or (DEP_M_VALS, DEP_M_P)
            k = rng.choice(n_vals, m, p=n_p)
            taken = np.zeros((m, 25), bool)

            def place(rows, cells):
                sub_g[rows, cells] = W
                sub_m[rows, cells] = np.maximum(rng.choice(m_vals, rows.size, p=m_p), floor)
                taken[rows, cells] = True

            # 1) guaranteed win: a cell on reels 1-3 whose conversion to W makes a line through it
            #    pay (the wild is inside the winning run, so its multiplier always counts)
            cand = np.zeros((m, 25), bool)
            for c in range(15):
                reel, row = divmod(c, 5)
                through = np.flatnonzero(LINES[:, reel] == row)
                if through.size == 0:
                    continue
                t = sub_g.copy()
                t[:, c] = W
                cand[:, c] = line_wins_plain(t.reshape(m, 5, 5))[:, through].any(1)
            keys = np.where(cand, rng.random((m, 25)), np.inf)
            has = np.isfinite(keys.min(1))
            rows = np.flatnonzero(has)
            place(rows, keys[rows].argmin(1))
            # fallback (no such cell): convert the reel 1 and reel 2 cells of a random line, skipping
            # cells already W or showing its reel 3 symbol, so that symbol pays at least 3 of a kind
            rows = np.flatnonzero(~has)
            if rows.size:
                ln = rng.integers(0, len(LINES), rows.size)
                s3 = sub_g[rows, 2 * 5 + LINES[ln, 2]]
                for reel in (0, 1):
                    cells = reel * 5 + LINES[ln, reel]
                    need = (sub_g[rows, cells] != s3) & (sub_g[rows, cells] != W)
                    place(rows[need], cells[need])
            # 2) remaining wilds on random free cells (total = max(k, wilds already placed))
            remaining = np.maximum(k - taken.sum(1), 0)
            if self.sharp_in_run:
                #    SHARPSHOOTER BOOST: every further wild lands inside a winning run
                place_in_run(sub_g, sub_m, taken, remaining, (m_vals, m_p), floor, rng, self.pay)
            else:
                keys = rng.random((m, 25))
                keys[taken] = np.inf
                rank = np.argsort(np.argsort(keys, axis=1), axis=1)
                sel = (rank < remaining[:, None]) & np.isfinite(keys)
                r_sel, c_sel = np.nonzero(sel)
                place(r_sel, c_sel)
            gf[idx], mf[idx] = sub_g, sub_m
            n_dep_wilds[idx] = taken.sum(1)

        # --- Line evaluation (best symbol per line, wilds substitute, per-line mult sum)
        Ls = g[:, REEL_IDX, LINES]          # (n, 20, 5)
        Lm = mult[:, REEL_IDX, LINES]
        isw = Ls == W
        best = np.zeros(Ls.shape[:2])
        for s in PAYING:
            run = np.logical_and.accumulate((Ls == s) | isw, axis=2)
            cnt = run.sum(2)
            p = self.pay[s][cnt]
            if not p.any():
                continue
            msum = (Lm * run).sum(2)
            np.maximum(best, p * np.where(msum > 0, msum, 1), out=best)
        line_win = best.sum(1)
        scat = (g == S).sum((1, 2))
        if landed:
            return line_win, scat, dep, n_dep_wilds, g_landed, m_landed
        if final:
            return line_win, scat, dep, n_dep_wilds, g, mult
        return line_win, scat, dep, n_dep_wilds


# ---------------------------------------------------------------------------
# Sharpshooter presentation (outcome-first; section 6)
# ---------------------------------------------------------------------------
PAY_ARR = paytable_array(C.PAYTABLE_DRAFT)
_LINE_CELLS = [[r * 5 + int(ln[r]) for r in range(5)] for ln in LINES]


def lines_eval(g, mult):
    """One board: g, mult (5, 5) [reel, row]. Engine semantics per line: max over paying symbols of
    pay x (sum of multipliers in the run, or 1 if 0). Returns (total, [(line, symbol, n, base pay,
    run cells)]) for the paying lines."""
    gf, mf = g.reshape(25), mult.reshape(25)
    total, det = 0.0, []
    for li, cells in enumerate(_LINE_CELLS):
        best = None
        for s in PAYING:
            n = 0
            while n < 5 and gf[cells[n]] in (s, W):
                n += 1
            p = PAY_ARR[s][n]
            if p:
                ms = int(mf[cells[:n]].sum())
                v = p * (ms if ms > 0 else 1)
                if best is None or v > best[0]:
                    best = (v, s, n, p)
        if best:
            total += best[0]
            det.append((li, best[1], best[2], best[3], _LINE_CELLS[li][:best[2]]))
    return total, det


def _present_candidates(gf, kmax, rng):
    """Wild cell sets (flat idx) that each build one line's run: for every line, paying symbol s and
    length n, the run cells showing neither s nor W must convert; any run cells showing s may convert
    too. Any cell can convert. Plus unions of two such sets (from a random sample)."""
    singles, out = [], set()
    for cells in _LINE_CELLS:
        for s in PAYING:
            for n in (3, 4, 5):
                if not PAY_ARR[s][n]:
                    continue
                run = cells[:n]
                need = [c for c in run if gf[c] != s and gf[c] != W]
                if len(need) > kmax:
                    continue
                pad = [c for c in run if gf[c] == s]
                singles.append((need, pad))
    for need, pad in singles:
        for r in range(len(pad) + 1):
            for add in itertools.combinations(pad, r):
                S = tuple(sorted(set(need) | set(add)))
                if 1 <= len(S) <= kmax:
                    out.add(S)
    base = sorted(out)
    rng.shuffle(base)
    for a, b in itertools.combinations(base[:C.SHARPSHOOTER_PRESENT_PAIR_SAMPLE], 2):
        S = tuple(sorted(set(a) | set(b)))
        if len(S) <= kmax:
            out.add(S)
    return sorted(out)


def _solve_mults(coef, target, vals):
    """All multiplier tuples m (each from vals) with sum(coef * m) == target."""
    sols = []
    order = sorted(range(len(coef)), key=lambda i: -coef[i])

    def rec(i, rem, acc):
        if i == len(order):
            if abs(rem) < 1e-9:
                sols.append(tuple(acc[j] for j in range(len(coef))))
            return
        c = coef[order[i]]
        rest_min = sum(coef[order[j]] for j in range(i + 1, len(order))) * vals[0]
        for v in vals:
            left = rem - c * v
            if left < rest_min - 1e-9:
                break
            acc[order[i]] = v
            rec(i + 1, left, acc)
    rec(0, target, {})
    return sols


def sharpshooter_presentation(g_landed, mult_landed, award, floor, n_forward, rng):
    """Rebuild a Sharpshooter spin's wilds to show exactly `award` with the most wilds (up to
    SHARPSHOOTER_PRESENT_MAX_WILDS). Every new wild lies in a winning run and carries a multiplier from
    SHARPSHOOTER_MULTS raised to >= floor; landed wilds keep their multipliers. Returns (cells, mults) with
    more than n_forward wilds, or None (keep the award procedure's own wilds)."""
    gf0, mf0 = g_landed.reshape(25), mult_landed.reshape(25)
    vals = sorted({max(int(v), floor) for v in C.SHARPSHOOTER_MULTS})
    by_k = {}
    for S in _present_candidates(gf0, C.SHARPSHOOTER_PRESENT_MAX_WILDS, rng):
        by_k.setdefault(len(S), []).append(S)
    for k in sorted(by_k, reverse=True):
        if k <= n_forward:
            break
        opts = by_k[k]
        rng.shuffle(opts)
        for S in opts:
            g = gf0.copy()
            g[list(S)] = W
            m0 = mf0.copy()
            m0[list(S)] = 0
            _, det = lines_eval(g.reshape(5, 5), m0.reshape(5, 5))
            const, coef = 0.0, np.zeros(k)
            for _, _, _, p, run in det:
                F = int(m0[run].sum())
                hits = [i for i, c in enumerate(S) if c in run]
                if hits:
                    const += p * F
                    coef[hits] += p
                else:
                    const += p * (F if F > 0 else 1)
            if (coef == 0).any():
                continue                                 # a wild outside every winning run
            sols = _solve_mults(list(coef), award - const, vals)
            rng.shuffle(sols)
            for m in sols:
                mf = mf0.copy()
                mf[list(S)] = m
                if abs(lines_eval(g.reshape(5, 5), mf.reshape(5, 5))[0] - award) < 1e-9:
                    return list(S), [int(v) for v in m]
    return None


def _sharp_award_job(args):
    strips, pays, sharp, n, seed = args
    sp = ReelSpinner(strips, pays, trigger_rate=1.0, sharp=sharp)
    rng = np.random.default_rng(seed)
    vals = np.array(list(sharp["mults"]))
    award = np.empty(n)
    counts = np.zeros((n, vals.size), np.uint8)
    done = 0
    while done < n:
        b = min(50_000, n - done)
        lw, _, _, _, _, mult = sp.spin(b, rng, 0, np.ones(b, bool), final=True)
        mf = mult.reshape(b, 25)
        award[done:done + b] = lw
        for j, v in enumerate(vals):
            counts[done:done + b, j] = (mf == v).sum(1)
        done += b
    return award, counts


def sharp_award_sample(strips, pays, sharp, n, seed, procs=8):
    """Forced Sharpshooter spins for a mode with its own Sharpshooter content (floor 0, no natural-wild
    multipliers, so every wild with a multiplier is a Sharpshooter wild). Returns (award per spin, count of
    each multiplier value placed per spin), in parallel. The counts let the multiplier weights be reweighted
    (importance weights) without re-spinning: placement depends on the draws, never on the weights."""
    from multiprocessing import get_context
    chunks = [n // procs + (i < n % procs) for i in range(procs)]
    with get_context("fork").Pool(procs) as pool:   # fork: run_model.py has no __main__ guard
        out = pool.map(_sharp_award_job, [(strips, pays, sharp, c, seed + i) for i, c in enumerate(chunks)])
    return np.concatenate([a for a, _ in out]), np.concatenate([c for _, c in out])


def reweighted_mean(award, counts, p_from, p_to):
    """Mean award under multiplier probabilities p_to, from a sample drawn with p_from (same value order)."""
    lr = np.exp(counts @ (np.log(p_to) - np.log(p_from)))
    return float((award * lr).sum() / lr.sum())


def reel_stats(spinner, n_total, rng, floor=0, forced=False):
    """Monte Carlo statistics of a normal (non-Showdown) reel spin."""
    acc = dict(n=0, line=0.0, line2=0.0, scat_pay=0.0, hit=0, dep=0, dep_line=0.0,
               s3=0, s4=0, s5=0, max_line=0.0, dep_wilds=0, dep_zero=0, profit=0, push=0, dep_wins=[])
    while acc["n"] < n_total:
        b = min(C.BATCH, n_total - acc["n"])
        fd = np.ones(b, bool) if forced else None
        lw, sc, dep, nw = spinner.spin(b, rng, floor, fd)
        tot = lw + spinner.scat_pay[sc]
        acc["n"] += b
        acc["line"] += lw.sum()
        acc["line2"] += (tot ** 2).sum()
        acc["scat_pay"] += spinner.scat_pay[sc].sum()
        acc["hit"] += (tot > 0).sum()
        acc["dep"] += dep.sum()
        acc["dep_line"] += lw[dep].sum()
        acc["dep_wilds"] += nw.sum()
        acc["dep_zero"] += (dep & (tot == 0)).sum()
        acc["profit"] += (tot > 1).sum()
        acc["push"] += ((tot > 0) & (tot <= 1)).sum()
        acc["dep_wins"].append(tot[dep])
        for k in (3, 4):
            acc[f"s{k}"] += (sc == k).sum()
        acc["s5"] += (sc >= 5).sum()
        acc["max_line"] = max(acc["max_line"], lw.max())
    n = acc["n"]
    st = {
        "E_line": acc["line"] / n, "E_scat_pay": acc["scat_pay"] / n,
        "E2_total": acc["line2"] / n, "hit_rate": acc["hit"] / n,
        "P_dep": acc["dep"] / n, "E_line_dep_share": acc["dep_line"] / n,
        "P_s3": acc["s3"] / n, "P_s4": acc["s4"] / n, "P_s5": acc["s5"] / n,
        "max_line": acc["max_line"], "n": n,
        "P_profit": acc["profit"] / n, "push_share_of_wins": acc["push"] / max(acc["hit"], 1),
        "dep_zero_share": acc["dep_zero"] / max(acc["dep"], 1),
    }
    dw = np.concatenate(acc["dep_wins"]) if acc["dep_wins"] else np.zeros(1)
    st.update({"dep_avg": float(dw.mean()), "dep_median": float(np.median(dw)),
               "dep_p10": float(np.percentile(dw, 10)), "dep_p90": float(np.percentile(dw, 90)),
               "dep_min": float(dw.min())})
    st["E_total"] = st["E_line"] + st["E_scat_pay"]
    return st


def scatter_probs_exact(strips, p_trig):
    """Exact P(k scatters visible) per normal reel spin, with the Sharpshooter / scatter exclusion:
    a Sharpshooter spin (chance p_trig) shows no scatters. dist[5] = P(5+).
    per_reel = each reel's unconditional window distribution (0 / 1 / 2 scatters visible)."""
    def window_counts(st, stops=None):
        L = len(st)
        isS = (st == S).astype(int)
        idx = np.arange(L) if stops is None else stops
        return np.array([isS[(i + np.arange(5)) % L].sum() for i in idx])

    per_reel = [np.bincount(window_counts(st), minlength=3) / len(st) for st in strips]
    dist = np.array([1.0])
    for w in per_reel:
        dist = np.convolve(dist, w)
    dist = (1 - p_trig) * dist
    dist[0] += p_trig
    out = np.zeros(6)
    out[:5] = dist[:5]
    out[5] = dist[5:].sum()
    return per_reel, out


# ---------------------------------------------------------------------------
# Showdown
# ---------------------------------------------------------------------------
def showdown_outcomes(mod_weights, table_key):
    """Every Showdown outcome as (label, modifier, payout, probability)."""
    pv, pp, px = mod_weights
    out = []
    cw = sum(w for _, w in C.CHARACTERS.values())
    for name, (v, w) in C.CHARACTERS.items():
        pc = pv * w / cw
        out.append((f"VS {name} - Sheriff wins", "VS", C.SHERIFF_VALUE + v, pc * C.SHERIFF_WIN_CHANCE))
        out.append((f"VS {name} - {name} wins", "VS", v, pc * (1 - C.SHERIFF_WIN_CHANCE)))
    for mod, pm, table in (("+", pp, C.PLUS_WEIGHTS[table_key]), ("X", px, C.X_WEIGHTS[table_key])):
        tw = sum(table)
        for num, w in zip(C.NUMBERS, table):
            pay = C.SHERIFF_VALUE + num if mod == "+" else C.SHERIFF_VALUE * num
            out.append((f"{mod}{num}", mod, min(pay, C.MAX_WIN), pm * w / tw))
    return out


def showdown_summary(outcomes):
    pays = np.array([o[2] for o in outcomes], float)
    probs = np.array([o[3] for o in outcomes])
    by_mod = {"VS": 0.0, "+": 0.0, "X": 0.0}
    for _, mod, pay, p in outcomes:
        by_mod[mod] = by_mod.get(mod, 0.0) + pay * p
    return {
        "EV": float(pays @ probs), "E2": float((pays ** 2) @ probs),
        "by_mod": by_mod,
        "P_max": float(probs[pays >= C.MAX_WIN].sum()),
        "P_10k": float(probs[pays >= 10_000].sum()),
        "pays": pays, "probs": probs,
    }


# ---------------------------------------------------------------------------
# Free spins: exact CONDITIONAL expectation via dynamic programming over
# (spins left, Showdowns so far (capped at the guarantee), Sharpshooter seen).
# Guarantees are met by redrawing: a round that ends without the tier's guaranteed Showdowns
# (and, for POSSE, a Sharpshooter) is discarded and replayed, exactly as book generation with a
# criteria filter does. Guaranteed events therefore land on random spins. The DP returns
# E[X | guarantees met] = E[X * 1{met}] / P(met).
# Sharpshooter spins show no scatters, so they never retrigger.
# ---------------------------------------------------------------------------
def tier_target(tier):
    """Average award a free-spin round must return: natural = its sized target, buy = RTP x price."""
    return tier["target_ev"] if tier["mode"] == "natural" else C.RTP_TARGET * tier["buy_price"]


def natural_keys():
    return [k for k, t in C.FREE_SPIN_TIERS.items() if t["mode"] == "natural"]


def buy_keys():
    return [k for k, t in C.FREE_SPIN_TIERS.items() if t["mode"] == "buy"]


def min_showdowns(tier):
    return tier.get("min_showdowns", 1 if "showdown" in tier["guarantees"] else 0)


def fs_dp(tier, reel, max_rem=250):
    """Expected reel win, Showdown count and spins for one round, conditional on the tier's
    guarantees; also the chance an unconditioned round meets them (book acceptance rate)."""
    p = tier["showdown_rate"]
    need = min_showdowns(tier)
    g_dep = "sharpshooter" in tier["guarantees"]
    d = reel["P_dep"]
    r_nd = {k: reel[f"P_s{k}"] / (1 - d) for k in (3, 4, 5)}       # scatter odds on non-Sharpshooter spins
    r_none = 1 - sum(r_nd.values())
    win_dep = reel["E_line_dep_share"] / d if d else 0.0
    win_nd = (reel["E_total"] - reel["E_line_dep_share"]) / (1 - d)
    cap = C.RETRIGGER_SPIN_CAP or max_rem

    def run(rw_sd, rw_dep, rw_nd):
        # P[s] = P(guarantees met | state), W[s] = E[future reward * 1{met} | state]
        P = np.zeros((max_rem + 1, need + 1, 2))
        W = np.zeros_like(P)
        for ms in range(need + 1):
            for md in (0, 1):
                P[0, ms, md] = float(ms == need and (md or not g_dep))
        for _ in range(200):
            P0, W0 = P.copy(), W.copy()
            for rem in range(1, max_rem + 1):
                for ms in range(need + 1):
                    for md in (0, 1):
                        nsd = min(ms + 1, need)
                        pv = p * P[rem - 1, nsd, md]
                        wv = p * (rw_sd * P[rem - 1, nsd, md] + W[rem - 1, nsd, md])
                        q = (1 - p) * d
                        pv += q * P[rem - 1, ms, 1]
                        wv += q * (rw_dep * P[rem - 1, ms, 1] + W[rem - 1, ms, 1])
                        q = (1 - p) * (1 - d)
                        for extra, pk in [(0, r_none)] + [(C.RETRIGGER_SPINS[k], v) for k, v in r_nd.items()]:
                            x = min(rem - 1 + extra, max_rem, cap)
                            pv += q * pk * P[x, ms, md]
                            wv += q * pk * (rw_nd * P[x, ms, md] + W[x, ms, md])
                        P[rem, ms, md], W[rem, ms, md] = pv, wv
            if max(np.abs(P - P0).max(), np.abs(W - W0).max()) < 1e-12:
                break
        s0 = (tier["spins"], 0, int(not g_dep))
        return P[s0], W[s0]

    p_met, w_reel = run(0.0, win_dep, win_nd)
    _, w_sd = run(1.0, 0.0, 0.0)
    _, w_spins = run(1.0, 1.0, 1.0)
    return {"EV_reel": w_reel / p_met, "n_sd": w_sd / p_met, "n_spins": w_spins / p_met, "P_met": p_met}


def solve_x_share(tier, target, dp):
    """Showdown award average needed, then the X share (VS absorbs the rest) that delivers it."""
    need = (target - dp["EV_reel"]) / dp["n_sd"]
    pp = tier["plus_share"]
    ev = {}
    for m, w in (("VS", (1, 0, 0)), ("+", (0, 1, 0)), ("X", (0, 0, 1))):
        ev[m] = showdown_summary(showdown_outcomes(w, tier["tables"]))["EV"]
    # need = (1-pp-x)*EV_vs + pp*EV_plus + x*EV_x
    x = (need - (1 - pp) * ev["VS"] - pp * ev["+"]) / (ev["X"] - ev["VS"])
    return x, need, ev


# ---------------------------------------------------------------------------
# Sampled free-spin rounds (validation / distribution)
# ---------------------------------------------------------------------------
def fs_sample(spinner, tier, sd_sum, R, rng):
    """R free-spin rounds that meet the tier's guarantees: rounds are played unforced and any
    round that misses a guarantee is discarded and replayed (guarantees land on random spins)."""
    out = {k: [] for k in ("raw", "sd_win", "n_sd", "spins")}
    got, played = 0, 0
    while got < R:
        r = _fs_play(spinner, tier, sd_sum, R - got, rng)
        played += r["ok"].size
        for k in out:
            out[k].append(r[k][r["ok"]])
        got += int(r["ok"].sum())
    res = {k: np.concatenate(v)[:R] for k, v in out.items()}
    res["win"] = np.minimum(res["raw"], C.MAX_WIN)
    res["acceptance"] = R / played
    return res


def _fs_play(spinner, tier, sd_sum, R, rng):
    p_sd = tier["showdown_rate"]
    rem = np.full(R, tier["spins"], dtype=np.int64)
    total = np.zeros(R)
    sd_total = np.zeros(R)
    n_sd = np.zeros(R, dtype=np.int64)
    spins = np.zeros(R, dtype=np.int64)
    g_dep = "sharpshooter" in tier["guarantees"]
    met_dep = np.full(R, not g_dep)
    floor = tier["wild_floor"]
    while True:
        a = np.flatnonzero(rem > 0)
        if a.size == 0:
            break
        is_sd = rng.random(a.size) < p_sd
        sd_rows = a[is_sd]
        if sd_rows.size:
            w = rng.choice(sd_sum["pays"], sd_rows.size, p=sd_sum["probs"])
            total[sd_rows] += w
            sd_total[sd_rows] += w
            n_sd[sd_rows] += 1
        reel_rows = a[~is_sd]
        for s0 in range(0, reel_rows.size, C.BATCH):
            rr = reel_rows[s0:s0 + C.BATCH]
            lw, sc, dep, _ = spinner.spin(rr.size, rng, floor)
            total[rr] += lw + spinner.scat_pay[sc]
            met_dep[rr] |= dep
            add = np.zeros(rr.size, dtype=np.int64)
            add[sc == 3] = C.RETRIGGER_SPINS[3]
            add[sc == 4] = C.RETRIGGER_SPINS[4]
            add[sc >= 5] = C.RETRIGGER_SPINS[5]
            rem[rr] += add
        rem[a] -= 1
        spins[a] += 1
        if C.RETRIGGER_SPIN_CAP:
            rem = np.minimum(rem, np.maximum(C.RETRIGGER_SPIN_CAP - spins, 0))
    ok = (n_sd >= min_showdowns(tier)) & met_dep
    return {"raw": total, "sd_win": sd_total, "n_sd": n_sd, "spins": spins, "ok": ok}


def build_strips_spread(counts, rng, gap=4):
    """
    Spread arrangement: each symbol's copies are spaced evenly along the strip (random phase and
    jitter), then a repair pass swaps positions so no symbol repeats within `gap` positions where
    possible (a 5-row window then shows up to 5 different symbols). Scatters are then placed
    evenly (max one visible per reel).
    """
    strips = []
    for r in range(5):
        keys, syms = [], []
        for s, per_reel in counts.items():
            n = int(round(per_reel[r] * C.STRIP_REPEAT))
            if n:
                phase = rng.random()
                keys += list((np.arange(n) + phase + rng.uniform(-0.35, 0.35, n)) / n)
                syms += [SYM[s]] * n
        body = [syms[i] for i in np.argsort(keys)]
        L = len(body)

        def clash(i, sym):
            return any(body[(i + d) % L] == sym for d in range(-gap, gap + 1) if d)

        for _ in range(3):
            for i in range(L):
                if not clash(i, body[i]):
                    continue
                for d in range(1, L):
                    j = (i + d) % L
                    a, b = body[i], body[j]
                    body[i], body[j] = b, a
                    if not clash(i, b) and not clash(j, a):
                        break
                    body[i], body[j] = a, b
        groups = C.SCATTER_GROUPS[r]
        n_s = sum(len(g) for g in groups)
        length = len(body) + n_s
        anchors = [int(round(i * length / len(groups))) for i in range(len(groups))]
        pos = {a + o for a, g in zip(anchors, groups) for o in g}
        body = body[::-1]
        strip = [S if i in pos else body.pop() for i in range(length)]
        if r == 2:
            _separate_h1_from_scatters(strip, gap)
        strips.append(np.array(strip, dtype=np.int8))
    return strips


def _separate_h1_from_scatters(strip, gap):
    """Reel 3: move each H1 that sits within 2 positions of a scatter, so H1 in the center cell
    never shares the window with a scatter (the old Deputized / scatter exclusion; kept so the strips are
    unchanged). Swaps keep the spread
    rule (no symbol repeats within `gap` positions)."""
    L = len(strip)
    s_pos = [i for i, x in enumerate(strip) if x == S]

    def near_s(i):
        return any(min((i - p) % L, (p - i) % L) <= 2 for p in s_pos)

    def clash(i, sym, skip):
        return any(strip[(i + d) % L] == sym and (i + d) % L != skip for d in range(-gap, gap + 1) if d)

    for i in range(L):
        if strip[i] != H1 or not near_s(i):
            continue
        for d in range(1, L):
            j = (i + d) % L
            a = strip[j]
            if a in (S, H1) or near_s(j) or clash(j, H1, i) or clash(i, a, j):
                continue
            strip[i], strip[j] = a, H1
            break
        else:
            raise AssertionError("reel 3: cannot separate H1 from scatters")


# ---------------------------------------------------------------------------
# Anticipation (presentation only)
# ---------------------------------------------------------------------------
def anticipation_strips(strips, spacing):
    """Per reel: the reel's own non-scatter symbols in strip order with a scatter inserted every
    `spacing` positions (never two in a 5-row window when spacing >= 5). Display only."""
    out = []
    for st in strips:
        body = [x for x in st if x != S]
        a = []
        for i, x in enumerate(body):
            if i % (spacing - 1) == 0:
                a.append(S)
            a.append(x)
        out.append(np.array(a, dtype=np.int8))
    return out


def anticipation_levels(g):
    """g: (n, 5, 5) final boards. Returns (n, 5) int8 per reel: 0 none, 1 light, 2 heavy.
    Every reel after the 2nd scatter anticipates:
    heavy: at least ANTICIPATION_HEAVY_SCATTERS scatters on the reels to the left (chasing POSSE /
           SHOWDOWN BONUS).
    light: at least ANTICIPATION_MIN_SCATTERS scatters on the reels to the left (and not heavy)."""
    has = (g == S).any(2)
    left = np.cumsum(has, 1) - has
    heavy = left >= C.ANTICIPATION_HEAVY_SCATTERS
    light = (left >= C.ANTICIPATION_MIN_SCATTERS) & ~heavy
    return np.where(heavy, 2, np.where(light, 1, 0)).astype(np.int8)


def near_miss_stats(spinner, n, rng):
    """Normal reel spins (base strips): anticipation frequency by level, landing and off-screen
    (padding) near-miss rates on flagged reels, and other natural near-misses."""
    acc = dict(n=0, lvl=np.zeros((3, 5)), any=0, heavy_any=0, trig=0, land=np.zeros(5), miss=np.zeros(5),
               pad=np.zeros(5), broken4=0, nondep=0)
    while acc["n"] < n:
        b = min(C.BATCH, n - acc["n"])
        g, dep, stops = spinner.grids(b, rng, return_stops=True)
        lv = anticipation_levels(g)
        has = (g == S).any(2)
        flag = lv > 0
        acc["n"] += b
        for k in (1, 2):
            acc["lvl"][k] += (lv == k).sum(0)
        acc["any"] += flag.any(1).sum()
        acc["heavy_any"] += (lv == 2).any(1).sum()
        acc["trig"] += ((g == S).sum((1, 2)) >= 3)[flag.any(1)].sum()
        acc["land"] += (flag & has).sum(0)
        miss = flag & ~has
        acc["miss"] += miss.sum(0)
        for r in range(5):
            st, L = spinner.strips[r], spinner.lens[r]
            pad = (st[(stops[r] - 1) % L] == S) | (st[(stops[r] + 5) % L] == S)
            acc["pad"][r] += (miss[:, r] & pad).sum()
        nd = ~dep
        acc["nondep"] += nd.sum()
        f = g[:, REEL_IDX, LINES]                     # (b, lines, 5)
        nonw4 = f[..., :4] != W
        hi = np.where(nonw4, f[..., :4], -1).max(2)
        lo = np.where(nonw4, f[..., :4], 127).min(2)
        four = (hi == lo) & (hi >= 0) & (hi != S)
        fifth = f[..., 4]
        acc["broken4"] += (nd & (four & (fifth != W) & (fifth != hi)).any(1)).sum()
    N = acc["n"]
    fl = acc["lvl"][1] + acc["lvl"][2]
    return {
        "P_light": acc["lvl"][1] / N, "P_heavy": acc["lvl"][2] / N,
        "P_any": acc["any"] / N, "P_heavy_any": acc["heavy_any"] / N,
        "P_trigger_given_any": acc["trig"] / max(acc["any"], 1),
        "P_land_given_flag": np.divide(acc["land"], fl, out=np.zeros(5), where=fl > 0),
        "P_padding_scatter_given_flag_miss": np.divide(acc["pad"], acc["miss"], out=np.zeros(5), where=acc["miss"] > 0),
        "P_line_4oak_broken_on_reel5": acc["broken4"] / N,
    }
