"""Re-solve the outline's four solved parameters at large sample sizes so every paid mode returns exactly 96.00%
(user decision 2026-09-30; the outline solved them from 4-8M-spin samples, and the frozen design came out at
95.86% base, 96.39% WILD Ante, 95.96% SHOWDOWN Ante and ~95.6% SHARPSHOOTER Ante in targets.py's larger model).

  1. base Showdown rate (shared by the base game, WILD Ante and SHARPSHOOTER Ante): closed form,
     r = (0.96 - A) / (EV_sd - A), A = a non-Showdown base spin's value (reel spin + natural bonuses).
  2. SHOWDOWN Ante's Showdown rate: closed form against 0.96 x 3.
  3. WILD Ante's natural-wild ladder tilt t (final weight = design weight x multiplier^t): the mode's non-Showdown
     spin value as a function of t, by importance-reweighting one large sample of WILD Ante spins drawn at the
     spec's current t (every landed wild draws from the ladder whatever happens next, so a spin's weight is the
     product of p_t(m) / p_t0(m) over its landed wilds).
  4. SHARPSHOOTER Ante's multiplier tilt t (final weight = design weight x multiplier^t): the forced Sharpshooter
     award as a function of t, by importance-reweighting one large sample (engine.sharp_award_sample, the outline's
     own method: placement depends on the draws, never on the weights).

Everything else (strips, natural bonuses, the other weights) is unchanged. Inputs: targets.json (run targets.py
first). Run: PYTHONPATH=. python3 games/sheriff_showdown/resolve.py  ->  resolved.json
"""

import json
import math
import os
import sys
from multiprocessing import get_context

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "reference"))

import spec  # noqa: E402
import targets as T  # noqa: E402

RTP = spec.RTP_TARGET
WILD_SPINS = 32_000_000  # WILD Ante normal + Sharpshooter spins at their natural mix
SHARP_ANTE_SPINS = 12_000_000
WILD_SEED = int(os.environ.get("RESOLVE_WILD_SEED", 4100))
SHARP_SEED = int(os.environ.get("RESOLVE_SHARP_SEED", 5100))
LADDER_DESIGN = {1: 45, 3: 30, 5: 15, 7: 4, 9: 2.5, 10: 2, 25: 1, 50: 0.5}  # outline config WILD_ANTE_WILD_MULTS
SHARP_ANTE_DESIGN = {int(k): v for k, v in spec.SPEC["antes"]["sharpshooter"]["multiplier_design_weights"].items()}


def tilted(design: dict, t: float) -> dict:
    return {m: w * m**t for m, w in design.items()}


def probs(table: dict, keys: list) -> np.ndarray:
    total = sum(table.values())
    return np.array([table[k] / total for k in keys])


def _wild_job(args):
    """WILD Ante spins at the spec's ladder, aggregated by their landed-ladder count vector: {counts: [spins, sum of
    value, sum of value^2]}, value = line win + scatter pay + the natural bonus's average (targets.json) on 3+ scatters."""
    n, seed, bonus_by_k = args
    C, E = T._engine()
    ladder = spec.BASE_MODES["wild_ante"]["wild_multipliers"]
    sp = T._spinner(E, C, "wild_ante", ladder, None, spec.SHARPSHOOTER_RATE["wild_ante"])
    rng = np.random.default_rng(seed)
    vals = sorted(ladder)
    agg = {}
    done = 0
    while done < n:
        b = min(T.BATCH, n - done)
        lw, sc, dep, _, g, m = sp.spin(b, rng, 0, landed=True)
        nat = g == E.W
        counts = np.stack([((m == v) & nat).sum(axis=(1, 2)) for v in vals], axis=1)
        value = lw + sp.scat_pay[sc] + np.where(dep, 0.0, np.array(bonus_by_k)[np.minimum(sc, 5)])
        uniq, inv = np.unique(counts, axis=0, return_inverse=True)
        inv = inv.reshape(-1)
        nn = np.bincount(inv, minlength=len(uniq))
        sv = np.bincount(inv, weights=value, minlength=len(uniq))
        s2 = np.bincount(inv, weights=value**2, minlength=len(uniq))
        for i, row in enumerate(map(tuple, uniq)):
            a = agg.setdefault(row, [0, 0.0, 0.0])
            a[0] += nn[i]
            a[1] += sv[i]
            a[2] += s2[i]
        done += b
    return agg


def _sharp_ante_job(args):
    n, seed = args
    C, E = T._engine()
    sharp = spec.BASE_MODES["sharpshooter_ante"]["sharpshooter"]
    strips = [np.array([E.SYM[s] for s in col], dtype=np.int8) for col in spec.STRIPS["base"]]
    content = {"counts": sharp["wild_count"], "mults": sharp["multipliers"], "in_run": sharp["in_run"]}
    return E._sharp_award_job((strips, C.PAYTABLE_DRAFT, content, n, seed))


def solve(fn, target: float, lo: float, hi: float) -> float:
    """Bisection for fn(t) = target, fn increasing."""
    assert fn(lo) < target < fn(hi), (fn(lo), target, fn(hi))
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if fn(mid) < target else (lo, mid)
    return (lo + hi) / 2


def main():
    with open(os.path.join(HERE, "targets.json"), encoding="UTF-8") as f:
        tg = json.load(f)
    bonus_ev = {fid: tg["bonus"][fid]["ev_uncapped"] for fid in ("sheriff", "posse", "showdown")}
    sd_ev = sum(award * p for _, award, p, _ in T.showdown_outcomes(spec.BASE_MODES["base"]["showdown"]))

    def non_showdown_value(name: str) -> float:
        cats = [c for c in tg["modes"][name]["categories"] if c["kind"] != "showdown"]
        p = sum(c["prob"] for c in cats)
        return sum(c["prob"] * c["mean"] for c in cats) / p

    # 1-2. Showdown rates (closed form).
    a_base = non_showdown_value("base")
    r_base = (RTP * 1 - a_base) / (sd_ev - a_base)
    r_sd_ante = (RTP * spec.BASE_MODES["showdown_ante"]["cost"] - a_base) / (sd_ev - a_base)
    print(f"base: non-Showdown spin {a_base:.6f}, Showdown EV {sd_ev:.6f} -> rate {r_base:.9f} (1 in {1 / r_base:.2f}; "
          f"spec {spec.BASE_MODES['base']['showdown']['rate']:.9f})", flush=True)
    print(f"SHOWDOWN Ante: rate {r_sd_ante:.9f} (1 in {1 / r_sd_ante:.3f}; spec {spec.BASE_MODES['showdown_ante']['showdown']['rate']:.9f})", flush=True)

    with get_context("fork").Pool(T.PROCS) as pool:
        # 3. WILD Ante ladder tilt.
        bonus_by_k = [0, 0, 0, bonus_ev["sheriff"], bonus_ev["posse"], bonus_ev["showdown"]]
        parts = pool.map(_wild_job, [(WILD_SPINS // T.PROCS, WILD_SEED + i, bonus_by_k) for i in range(T.PROCS)])
        agg = {}
        for part in parts:
            for row, (nn, sv, s2) in part.items():
                a = agg.setdefault(row, [0, 0.0, 0.0])
                a[0] += nn
                a[1] += sv
                a[2] += s2
        rows = np.array(list(agg), dtype=np.float64)
        n_row = np.array([v[0] for v in agg.values()], dtype=np.float64)
        sum_row = np.array([v[1] for v in agg.values()])
        sq_row = np.array([v[2] for v in agg.values()])
        ladder0 = spec.BASE_MODES["wild_ante"]["wild_multipliers"]
        vals = sorted(ladder0)
        logp0 = np.log(probs(ladder0, vals))

        def wild_value(t: float) -> float:
            lr = np.exp(rows @ (np.log(probs(tilted(LADDER_DESIGN, t), vals)) - logp0))
            return float((sum_row * lr).sum() / (n_row * lr).sum())

        t0 = float(os.environ.get("RESOLVE_WILD_T0", 0.14705810546874998))  # the tilt the spec's ladder was drawn at
        target_wild = (RTP * spec.BASE_MODES["wild_ante"]["cost"] - r_base * sd_ev) / (1 - r_base)
        t_wild = solve(wild_value, target_wild, -1.0, 1.0)
        n_wild = n_row.sum()
        mean_wild = sum_row.sum() / n_wild
        se_wild = float(math.sqrt((sq_row.sum() / n_wild - mean_wild**2) / n_wild))
        print(f"WILD Ante: value at spec t {wild_value(t0):.5f} (+/- {se_wild:.5f}), target {target_wild:.5f} -> t {t_wild:.6f} (spec {t0:.6f})", flush=True)

        # 4. SHARPSHOOTER Ante multiplier tilt.
        parts = pool.map(_sharp_ante_job, [(SHARP_ANTE_SPINS // T.PROCS, SHARP_SEED + i) for i in range(T.PROCS)])
        award = np.concatenate([p[0] for p in parts])
        mcnt = np.concatenate([p[1] for p in parts]).astype(np.float64)
    mvals = sorted(spec.BASE_MODES["sharpshooter_ante"]["sharpshooter"]["multipliers"])
    p_from = probs(spec.BASE_MODES["sharpshooter_ante"]["sharpshooter"]["multipliers"], mvals)

    def sharp_award(t: float) -> float:
        lr = np.exp(mcnt @ (np.log(probs(tilted(SHARP_ANTE_DESIGN, t), mvals)) - np.log(p_from)))
        return float((award * lr).sum() / lr.sum())

    sa = spec.BASE_MODES["sharpshooter_ante"]
    d = sa["sharpshooter"]["rate"]
    # The mode's non-Sharpshooter reel spins are base reel spins (+ natural bonuses): A_base without its Sharpshooter part.
    d_base = spec.SHARPSHOOTER_RATE["base"]
    base_sharp = tg["stats"]["sharp"]["base"]["mean"]
    a_normal = (a_base - d_base * base_sharp) / (1 - d_base)
    target_award = ((RTP * sa["cost"] - r_base * sd_ev) / (1 - r_base) - (1 - d) * a_normal) / d
    t_sharp0 = spec.SPEC["antes"]["sharpshooter"]["multiplier_tilt"]
    t_sharp = solve(sharp_award, target_award, 0.5, 2.5)
    se_award = float(award.std() / math.sqrt(len(award)))
    print(f"SHARPSHOOTER Ante: award at spec t {sharp_award(t_sharp0):.3f} (+/- {se_award:.3f}), target {target_award:.3f} "
          f"-> t {t_sharp:.6f} (spec {t_sharp0:.6f})", flush=True)

    out = {
        "base_showdown_rate": r_base,
        "showdown_ante_rate": r_sd_ante,
        "wild_ante_tilt": t_wild,
        "wild_ante_weights": tilted(LADDER_DESIGN, t_wild),
        "sharpshooter_ante_tilt": t_sharp,
        "sharpshooter_ante_weights": tilted(SHARP_ANTE_DESIGN, t_sharp),
        "sharpshooter_ante_target_award": target_award,
        "inputs": {
            "a_base": a_base, "showdown_ev": sd_ev, "wild_value_target": target_wild, "wild_spins": int(n_wild),
            "wild_value_se": se_wild, "sharp_ante_spins": len(award), "sharp_award_se": se_award,
            "a_normal": a_normal,
        },
    }
    with open(os.path.join(HERE, "resolved.json"), "w", encoding="UTF-8") as f:
        json.dump(out, f, indent=1)
    print("wrote resolved.json")


if __name__ == "__main__":
    main()
