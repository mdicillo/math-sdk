"""Exact category model for the published weights (user decision 2026-09-30: weights from the spec's exact
probabilities, tuned within each category only enough to land 96.00%).

Every bet mode's outcomes are split into categories whose probabilities follow exactly from the spec:
  - paid modes: one category per Showdown outcome (chance per spin x outcome probability); the Sharpshooter spin;
    the ordinary reel spin (no Sharpshooter, fewer than 3 scatters); and, per natural bonus tier (3 / 4 / 5
    scatters), one category per "big X" class of the free-spins round (below);
  - buy modes: one category per big X class of the bought round.
A free-spins round's big X class is the largest X number among its Showdowns (X25 ... X5000), "none" when it has
none of those (VS / + / X10 only). The Showdown outcomes are drawn independently of everything else in the round,
so P(class) follows exactly from the distribution of the round's Showdown count, which a forward dynamic program
over (spins left, Showdowns so far, Sharpshooter seen) gives exactly - with the guarantees met by redrawing, as the
game plays. The same program carries each count's expected reel-spin win, so every category also gets its expected
award. An X5000 round always settles at the 50,000x cap.

What is not exact: a reel spin's average line win (by scatter count) and the Sharpshooter's average award. Those
come from large Monte-Carlo samples of the outline's own vectorized engine (reference/engine.py, copied verbatim
from the outline; its rules match the port's, steps 1-2). Every number the model needs from the spec is read from
math_spec.json.

Run (from the repo root): PYTHONPATH=. python3 games/sheriff_showdown/targets.py  ->  targets.json (checked in).
"""

import json
import math
import os
import sys
from itertools import product
from multiprocessing import get_context

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "reference"))

import spec  # noqa: E402

SEED = 20261001
# Monte-Carlo sizes: normal (non-Sharpshooter) reel spins per strip context, and forced Sharpshooter spins.
REEL_SPINS = 24_000_000
SHARP_SPINS = 4_000_000
SHARP_ANTE_SPINS = 2_000_000
BATCH = 250_000
PROCS = 8

# Big X classes, smallest first; "none" = a round whose Showdowns are VS / + / X10 only.
X_CLASSES = ["none", 25, 50, 100, 250, 500, 1000, 5000]
CAP = spec.WINCAP_X


# --- Exact scatter odds ----------------------------------------------------------------------------------------


def scatter_reel_probs(strip_id: str) -> list:
    """Per reel, the share of stops whose window shows a scatter (at most one per window, checked)."""
    out = []
    for strip in spec.STRIPS[strip_id]:
        length = len(strip)
        counts = [sum(strip[(i + r) % length] == spec.SCATTER for r in range(spec.ROWS)) for i in range(length)]
        assert max(counts) <= 1, f"{strip_id}: two scatters visible on one reel"
        out.append(sum(counts) / length)
    return out


def scatter_count_probs(strip_id: str) -> list:
    """Exact P(k scatters) on a normal (non-Sharpshooter) reel spin, k = 0..5."""
    p = scatter_reel_probs(strip_id)
    dist = [0.0] * 6
    for bits in product((0, 1), repeat=spec.REELS):
        prob = 1.0
        for b, pr in zip(bits, p):
            prob *= pr if b else 1 - pr
        dist[sum(bits)] += prob
    return dist


# --- Monte-Carlo reel statistics (outline engine) ----------------------------------------------------------------


def _engine():
    import config as C
    import engine as E

    # The engine reads the solved Sharpshooter weights from math_spec, never config.py's design weights.
    E.set_wild_count_weights(spec.SHARPSHOOTER_WILD_COUNT)
    assert {int(k): v for k, v in C.SHARPSHOOTER_MULTS.items()} == spec.SHARPSHOOTER_MULTIPLIERS
    assert {s: tuple(v) for s, v in C.PAYTABLE_DRAFT.items()} == {
        s: tuple(spec.PAYTABLE[s][n] for n in (3, 4, 5)) for s in spec.PAYING_SYMBOLS
    }
    return C, E


def _spinner(E, C, strip_id, ladder, sharp, rate):
    strips = [np.array([E.SYM[s] for s in col], dtype=np.int8) for col in spec.STRIPS[strip_id]]
    content = None
    if sharp:
        content = {"counts": sharp["wild_count"], "mults": sharp["multipliers"], "in_run": sharp["in_run"]}
    return E.ReelSpinner(strips, C.PAYTABLE_DRAFT, wild_mults=ladder, trigger_rate=rate, sharp=content)


def _reel_job(args):
    """Normal reel spins: per scatter count k, the number of spins and the sum of line wins."""
    strip_id, floor, ladder, n, seed = args
    C, E = _engine()
    sp = _spinner(E, C, strip_id, ladder, None, 0.0)
    rng = np.random.default_rng(seed)
    cnt, line = np.zeros(6), np.zeros(6)
    done = 0
    while done < n:
        b = min(BATCH, n - done)
        lw, sc, dep, _ = sp.spin(b, rng, floor)
        assert not dep.any()
        k = np.minimum(sc, 5)
        cnt += np.bincount(k, minlength=6)[:6]
        line += np.bincount(k, weights=lw, minlength=6)[:6]
        done += b
    return cnt, line


def _sharp_job(args):
    """Forced Sharpshooter spins: count, sum and sum of squares of the award."""
    strip_id, floor, ladder, sharp, n, seed = args
    C, E = _engine()
    sp = _spinner(E, C, strip_id, ladder, sharp, 1.0)
    rng = np.random.default_rng(seed)
    s = s2 = 0.0
    done = 0
    while done < n:
        b = min(BATCH // 5, n - done)
        lw, sc, dep, _ = sp.spin(b, rng, floor, np.ones(b, bool))
        assert dep.all() and not sc.any()
        s += lw.sum()
        s2 += (lw**2).sum()
        done += b
    return n, s, s2


def reel_stats(pool, strip_id, floor=0, ladder=None, seed=0) -> dict:
    """Average win of a normal reel spin by scatter count: line win (k >= 3 pooled, the counts being rare) plus the
    exact scatter pay."""
    parts = pool.map(_reel_job, [(strip_id, floor, ladder, REEL_SPINS // PROCS, seed + i) for i in range(PROCS)])
    cnt = sum(p[0] for p in parts)
    line = sum(p[1] for p in parts)
    pooled = line[3:].sum() / cnt[3:].sum()
    win = []
    for k in range(6):
        lm = line[k] / cnt[k] if k < 3 else pooled
        win.append(lm + spec.SCATTER_PAYS.get(min(k, max(spec.SCATTER_PAYS)), 0))
    return {"win_by_scatters": win, "spins": int(cnt.sum()), "line_mean_k_ge_3": pooled, "k_ge_3_spins": int(cnt[3:].sum())}


def sharp_stats(pool, strip_id, floor=0, ladder=None, sharp=None, n=SHARP_SPINS, seed=0) -> dict:
    parts = pool.map(_sharp_job, [(strip_id, floor, ladder, sharp, n // PROCS, seed + i) for i in range(PROCS)])
    m = sum(p[0] for p in parts)
    s = sum(p[1] for p in parts)
    s2 = sum(p[2] for p in parts)
    mean = s / m
    return {"mean": mean, "se": math.sqrt((s2 / m - mean**2) / m), "spins": m}


# --- Showdown outcomes (exact) -----------------------------------------------------------------------------------


def showdown_outcomes(ctx: dict) -> list:
    """Every outcome of one Showdown draw in a context: (label, award x bet capped, probability, big X class)."""
    out = []
    tables = spec.NUMBER_TABLES[ctx["table"]]
    mods = ctx["modifiers"]
    total_mod = sum(mods.values())
    cw = sum(spec.CHALLENGER_WEIGHTS.values())
    for cid, w in spec.CHALLENGER_WEIGHTS.items():
        pc = mods["VS"] / total_mod * w / cw
        v = spec.CHALLENGERS[cid]
        out.append((f"VS_{cid}_sheriff", min(spec.SHERIFF_VALUE + v, CAP), pc * spec.SHERIFF_WIN_CHANCE, "none"))
        out.append((f"VS_{cid}_challenger", min(v, CAP), pc * (1 - spec.SHERIFF_WIN_CHANCE), "none"))
    for mod in ("PLUS", "X"):
        table = tables[mod]
        tw = sum(table.values())
        for num, w in table.items():
            award = spec.SHERIFF_VALUE + num if mod == "PLUS" else spec.SHERIFF_VALUE * num
            cls = num if mod == "X" and num in X_CLASSES else "none"
            out.append((f"{mod}_{num}", min(award, CAP), mods[mod] / total_mod * w / tw, cls))
    assert abs(sum(o[2] for o in out) - 1) < 1e-12
    return out


# --- Free-spins round (exact dynamic program) --------------------------------------------------------------------


def fs_count_distribution(mode: dict, reel: dict, sharp_mean: float, nmax: int = 400, rmax: int = 600) -> dict:
    """Forward dynamic program over one free-spins round. Each spin: a Showdown with the mode's chance; else a
    Sharpshooter spin with the strips' chance (no scatters); else a normal reel spin with k scatters (exact odds),
    k >= 3 adding RETRIGGER_SPINS. Rounds that end without the guarantees are redrawn, i.e. the result is
    conditioned on them. Returns P(n Showdowns | guarantees met), E[reel-spin win x 1{n} | met], E[spins | met], and
    P(met) (the share of rounds kept on the first draw)."""
    p = mode["showdown"]["rate"]
    d = spec.SHARPSHOOTER_RATE[mode["strips"]]
    pk = scatter_count_probs(mode["strips"])
    top = max(spec.RETRIGGER_SPINS)
    add = [spec.RETRIGGER_SPINS[min(k, top)] if k >= 3 else 0 for k in range(6)]
    assert spec.RETRIGGER_CAP is None, "the program assumes uncapped retriggers"
    w = reel["win_by_scatters"]

    M = np.zeros((rmax + 1, nmax + 1, 2))  # probability mass by (spins left, Showdowns, Sharpshooter seen)
    R = np.zeros_like(M)  # reel-spin win mass
    S = np.zeros_like(M)  # spins-played mass
    M[mode["spins"], 0, 0] = 1.0
    TM = np.zeros((nmax + 1, 2))
    TR = np.zeros_like(TM)
    TS = np.zeros_like(TM)
    lost = 0.0
    for _ in range(100_000):
        TM += M[0]
        TR += R[0]
        TS += S[0]
        M[0] = R[0] = S[0] = 0
        live = M.sum()
        if live < 1e-16:
            break
        nM, nR, nS = np.zeros_like(M), np.zeros_like(M), np.zeros_like(M)
        a, ar, asp = M[1:], R[1:], S[1:] + M[1:]  # every live round plays one more spin
        # Showdown: n + 1
        nM[:-1, 1:, :] += p * a[:, :-1, :]
        nR[:-1, 1:, :] += p * ar[:, :-1, :]
        nS[:-1, 1:, :] += p * asp[:, :-1, :]
        lost += p * a[:, -1, :].sum()
        # Sharpshooter spin: seen = 1, its award, never a retrigger
        q = (1 - p) * d
        sm = a.sum(axis=2)
        nM[:-1, :, 1] += q * sm
        nR[:-1, :, 1] += q * (ar.sum(axis=2) + sharp_mean * sm)
        nS[:-1, :, 1] += q * asp.sum(axis=2)
        # Normal reel spin with k scatters
        for k in range(6):
            q = (1 - p) * (1 - d) * pk[k]
            if q == 0:
                continue
            shift = add[k]  # spins left: rem - 1 + add
            src = slice(0, rmax - shift) if shift > 0 else slice(0, rmax)
            dst = slice(shift, rmax) if shift > 0 else slice(0, rmax)
            nM[dst] += q * a[src]
            nR[dst] += q * (ar[src] + w[k] * a[src])
            nS[dst] += q * asp[src]
            if shift > 0:
                lost += q * a[rmax - shift :].sum()
        M, R, S = nM, nR, nS
    else:
        raise RuntimeError("free-spins program did not converge")
    assert lost < 1e-12, f"truncated mass {lost}"
    n = np.arange(nmax + 1)
    met = (n[:, None] >= mode["min_showdowns"]) & ((np.arange(2)[None, :] == 1) | (not mode["needs_sharpshooter"]))
    p_met = TM[met].sum()
    pn = np.where(met, TM, 0).sum(axis=1) / p_met
    rn = np.where(met, TR, 0).sum(axis=1) / p_met
    spins = np.where(met, TS, 0).sum() / p_met
    return {"p_n": pn, "reel_n": rn, "spins": spins, "p_met": p_met, "p_total": TM.sum()}


def bonus_classes(mode: dict, dist: dict) -> dict:
    """Per big X class: probability, expected uncapped award (reel spins + Showdowns), and the conditional pieces the
    book generator needs (P(n | class) is p_n x (F_c^n - F_{c-1}^n) / P(class))."""
    outs = showdown_outcomes(mode["showdown"])
    rank = {c: i for i, c in enumerate(X_CLASSES)}
    q = np.zeros(len(X_CLASSES))  # P(one Showdown is class c)
    g = np.zeros(len(X_CLASSES))  # E[award x 1{class c}]
    for _, award, prob, cls in outs:
        q[rank[cls]] += prob
        g[rank[cls]] += prob * award
    F, G = np.cumsum(q), np.cumsum(g)
    n = np.arange(len(dist["p_n"]))
    out = {}
    for i, c in enumerate(X_CLASSES):
        Fc, Gc = F[i], G[i]
        Fp, Gp = (F[i - 1], G[i - 1]) if i else (0.0, 0.0)
        pc_n = Fc**n - (Fp**n if i else 0.0)
        pc = float((dist["p_n"] * pc_n).sum())
        sd = float((dist["p_n"] * n * (Gc * Fc ** np.maximum(n - 1, 0) - (Gp * Fp ** np.maximum(n - 1, 0) if i else 0))).sum())
        rl = float((dist["reel_n"] * pc_n).sum())
        out[str(c)] = {"prob": pc, "mean_uncapped": (rl + sd) / pc if pc > 0 else 0.0}
    assert abs(sum(v["prob"] for v in out.values()) - 1) < 1e-9
    return out


# --- Categories per bet mode -------------------------------------------------------------------------------------


def build(pool) -> dict:
    stats = {"reels": {}, "sharp": {}}
    seed = SEED
    # Normal reel spins: the paid strips (WILD Ante with its ladder) and every free-spins mode with its floor.
    for key, strip_id, floor, ladder in [
        ("base", "base", 0, None),
        ("wild_ante", "wild_ante", 0, spec.BASE_MODES["wild_ante"]["wild_multipliers"]),
    ] + [(fid, m["strips"], m["wild_floor"], None) for fid, m in spec.FREE_SPINS_MODES.items()]:
        seed += 100
        stats["reels"][key] = reel_stats(pool, strip_id, floor, ladder, seed)
        print(f"reel stats {key}: {stats['reels'][key]['win_by_scatters'][:3]}", flush=True)
    # Sharpshooter awards: the paid modes' and every free-spins mode's (shared content raised to its floor).
    for key, strip_id, floor, ladder, sharp, n in [
        ("base", "base", 0, None, None, SHARP_SPINS),
        ("wild_ante", "wild_ante", 0, spec.BASE_MODES["wild_ante"]["wild_multipliers"], None, SHARP_SPINS),
        ("sharpshooter_ante", "base", 0, None, spec.BASE_MODES["sharpshooter_ante"]["sharpshooter"], SHARP_ANTE_SPINS),
    ] + [(fid, m["strips"], m["wild_floor"], None, None, SHARP_SPINS) for fid, m in spec.FREE_SPINS_MODES.items()]:
        seed += 100
        stats["sharp"][key] = sharp_stats(pool, strip_id, floor, ladder, sharp, n, seed)
        print(f"sharp stats {key}: {stats['sharp'][key]}", flush=True)

    bonus = {}
    for fid, m in spec.FREE_SPINS_MODES.items():
        dist = fs_count_distribution(m, stats["reels"][fid], stats["sharp"][fid]["mean"])
        classes = bonus_classes(m, dist)
        ev = sum(v["prob"] * v["mean_uncapped"] for v in classes.values())
        bonus[fid] = {
            "classes": classes,
            "ev_uncapped": ev,
            "p_met": dist["p_met"],
            "avg_showdowns": float((np.arange(len(dist["p_n"])) * dist["p_n"]).sum()),
            "avg_spins": dist["spins"],
            "p_n": [float(x) for x in dist["p_n"][: int(np.nonzero(dist["p_n"] > 1e-18)[0].max()) + 1]],
            "reel_n": [float(x) for x in dist["reel_n"][: int(np.nonzero(dist["p_n"] > 1e-18)[0].max()) + 1]],
        }
        print(f"bonus {fid}: EV {ev:.3f} (spec {m['target_return']}), kept first draw {dist['p_met']:.4f}, "
              f"Showdowns {bonus[fid]['avg_showdowns']:.3f}, spins {dist['spins']:.3f}", flush=True)

    modes = {}
    for name, mode in spec.BASE_MODES.items():
        strips = mode["strips"]
        r = mode["showdown"]["rate"]
        sharp = mode.get("sharpshooter")
        d = sharp["rate"] if sharp else spec.SHARPSHOOTER_RATE[strips]
        pk = scatter_count_probs(strips)
        win = stats["reels"]["wild_ante" if strips == "wild_ante" else "base"]["win_by_scatters"]
        sharp_key = name if name in stats["sharp"] else "base"
        cats = []
        for label, award, prob, _ in showdown_outcomes(mode["showdown"]):
            if prob > 0:
                cats.append({"name": f"sd_{label}", "kind": "showdown", "outcome": label, "prob": r * prob, "mean": award})
        cats.append({"name": "sharpshooter", "kind": "sharpshooter", "prob": (1 - r) * d, "mean": stats["sharp"][sharp_key]["mean"]})
        p_ord = sum(pk[:3])
        cats.append({
            "name": "basegame", "kind": "ordinary", "prob": (1 - r) * (1 - d) * p_ord,
            "mean": sum(pk[k] * win[k] for k in range(3)) / p_ord,
        })
        for k, fid in ((3, "sheriff"), (4, "posse"), (5, "showdown")):
            for cls, cv in bonus[fid]["classes"].items():
                mean = CAP if cls == "5000" else win[k] + cv["mean_uncapped"]
                cats.append({
                    "name": f"{fid}_{cls}", "kind": "bonus", "scatters": k, "bonus": fid, "x_class": cls,
                    "prob": (1 - r) * (1 - d) * pk[k] * cv["prob"], "mean": mean,
                })
        modes[name] = {"cost": mode["cost"], "categories": cats}
    for name, buy in spec.BUY_MODES.items():
        fid = buy["free_spins"]["id"]
        cats = [
            {"name": f"{fid}_{cls}", "kind": "bonus", "scatters": 0, "bonus": fid, "x_class": cls, "prob": cv["prob"],
             "mean": CAP if cls == "5000" else cv["mean_uncapped"]}
            for cls, cv in bonus[fid]["classes"].items()
        ]
        modes[name] = {"cost": buy["cost"], "categories": cats}
    for name, m in modes.items():
        total_p = sum(c["prob"] for c in m["categories"])
        assert abs(total_p - 1) < 1e-9, f"{name}: probabilities sum to {total_p}"
        m["model_rtp"] = sum(c["prob"] * c["mean"] for c in m["categories"]) / m["cost"]
        print(f"{name}: model RTP {m['model_rtp'] * 100:.4f}% over {len(m['categories'])} categories", flush=True)
    return {"seed": SEED, "x_classes": [str(c) for c in X_CLASSES], "stats": stats, "bonus": bonus, "modes": modes}


if __name__ == "__main__":
    with get_context("fork").Pool(PROCS) as pool:
        out = build(pool)
    with open(os.path.join(HERE, "targets.json"), "w", encoding="UTF-8") as f:
        json.dump(out, f, indent=1)
    print("wrote targets.json")
