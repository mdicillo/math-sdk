Skull Raiders — Stake Engine math-SDK port
==========================================

Source of truth: the TypeScript fake-math dev model in the castle-raid (Skull Raiders) repo
(src/config/gameConfig.ts et al). Code wins over docs. Every bet mode targets 96% RTP. Wincap 10,000x.
Buy prices (bonus_1=100x, bonus_2=150x, bonus_mystery=300x) are the premium for immediacy and are
DECOUPLED from RTP — the optimizer weights each mode's outcomes to 96% independently.

Game: 5x5, 15 paylines, multiplier WILDs (sum within a line), a three-tier free-spins bonus
(BONUS/SUPER/HIDDEN = 8/12/15 spins on 3/4/5 scatters), a random raid-wheel event (ATTACK/STEAL),
two per-spin ante boosts (bonusChance, wheelChance) and a mystery bonus buy. SDK codes: W=wild, S=scatter.

Milestone log
-------------
A (done): grid, 15 paylines, paytable (displayed-x units), symbols, base(BR0)+feature(FR0,FR3) reels,
   wincap, base LINES eval + stock free-spins loop, base+feature multiplier-wild bags. Units verified:
   10,472 unmultiplied line wins all == paytable*100; multiplier factor = summed >=2 wilds within a line.
   Forced-wincap distribution deferred to F (no round can reach 10,000x yet).
B (folded into A): multiplier wilds already live in base+feature; units + factor verified.
C (done): 3 tiers (3/4/5 -> t1/t2/t3, 8/12/15 spins) + naturalMaxTier=2 clamp (natural never awards
   HIDDEN) + retrigger capped at bonus_max=30; per-tier feature reel (natural FR0 / bought FRB / tier3
   FR3) via get_current_distribution_conditions repoint. Verified: base yields only t1/t2; bonus yields
   t1/t2/t3; tot_fs never exceeds 30; tier-3 boards draw wild-22 density vs wild-14 for t1/t2.
   TODO (F): feature wincap-room early-end (clamp each feature board to remaining cap and stop).
D (todo): raid wheel custom events (wheelSpin/wheelConvert/wheelSteal); ATTACK + STEAL; as its own
   base-game criteria with a force flag so the optimizer can pin the ~22.9% wheel contribution.
E (todo): all 7 bet modes (base; base_bonuschance/base_wheelchance/base_bonuschance_wheelchance antes;
   bonus_1/bonus_2/bonus_mystery buys) with costs 1/3/5/8/100/150/300.
F (todo): game_optimization opt_params per mode summing to 0.96; WCAP tail reel; full `make run`
   100k/mode; every mode 96% + 3-star volatility band; PAR sheet; lock MODE_RTP in the game repo.
