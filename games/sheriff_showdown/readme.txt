# Sheriff Showdown

5 reels x 5 rows, 10 fixed paylines, left to right. Pays are x total bet per line, lines summed (no division by the
line count). W substitutes for every paying symbol, never for S; scatters pay anywhere (3/4/5 = 2x/10x/50x).
Max win 50,000x per round in every mode; the round ends there. Every mode targets 96% RTP.

Source of truth: the math outline (Dropbox JackslotAudio/SheriffShowdown/; PICKUP.md, math/output/math_spec.md).
Its math_spec.json and strips/*.csv are copied verbatim here (math_spec.json, reels/) and loaded by spec.py, so no
value is transcribed by hand; re-copy them when the outline is regenerated (the game repo keeps the same copies in
src/rgs/sheriff/data/). The outline's engine.py is the reference implementation; the game client's
src/rgs/sheriff/engine.ts is its TypeScript port, and the rules here follow it function for function.
The math is frozen (user, 2026-09-30): the outline as of its 2026-09-29 update. Buy prices 100x / 300x / 500x are final.

Books carry the spec's section 14 events (reveal, showdown, sharpshooter, winInfo, setTotalWin, bonusTrigger,
bonusStart, bonusRetrigger, bonusUpdate, bonusEnd, finalWin), not the SDK's standard events; money fields are book
units (100 = 1.00x). Parity: in the game repo, `npm run parity:sdk` replays every book against the client's own
math and must report 0 differences before any cert run or upload.

Bet modes (spec section 14.3):
  base               1x
  wild_ante          3x   WILD Ante (wild_ante strips; every landed wild carries a multiplier)
  showdown_ante      3x   SHOWDOWN Ante (Showdown about 1 in 10)
  sharpshooter_ante  60x  SHARPSHOOTER Ante (Sharpshooter 1 in 5 reel spins, its own content)
  buy_sheriff        100x SHERIFF BONUS buy
  buy_posse          300x POSSE BONUS buy
  buy_showdown       500x SHOWDOWN BONUS buy

Reels (reels/*.csv, `position,reel1..reel5`, position 1 = top; reels differ in length, so spec.read_strip_csv reads
them instead of the SDK's read_reels_csv): base, wild_ante, fs_sheriff, fs_posse, fs_showdown, fs_buy_sheriff,
fs_buy_posse, fs_buy_showdown. The outline's anticipation_* strips are display-only (the client spins reels on them)
and are not math reelsets.

Custom events beyond step 1: `showdown` {board, gameType, modifier, sheriffValue, challenger?, winner?, number?,
awardX, amount} instead of reveal + winInfo on a Showdown spin; bonusTrigger / bonusStart / bonusRetrigger /
bonusUpdate / bonusEnd around a free-spins round (spec 14.5); `sharpshooter` {wilds: [{reel, row, from, multiplier}], guaranteed: {cells, fallback},
board, multipliers} after reveal, before winInfo (rows 0-4; there are no padding rows in the game's events).

Running:
  PYTHONPATH=. python3 games/sheriff_showdown/run_debug.py   sims only, readable books, config files (10,000 a mode)

Port status:
  Step 1 - grid, paytable, paylines, exact strips, the four reel-spin modes: normal reel spins with line and scatter
           pays, anticipation and off-screen padding (no wild multipliers, Sharpshooter, Showdown or free spins yet;
           a 3+ scatter board pays its scatter pay only). Events: reveal, winInfo, setTotalWin, finalWin.
           Verified: exact expected reel-spin win (per-line enumeration over strip frequencies + exact scatter
           windows) base 0.40487x, wild_ante strips 0.54746x, matching engine.py (0.4050 / 0.5481 at 8M spins);
           line evaluation identical to engine.lines_eval on 160,000 boards (all strip sets, random multipliers);
           parity:sdk 0 differences on 40,000 books.
  Step 2 - wild multipliers and the Sharpshooter (sections 5-7): WILD Ante's natural-wild ladder; the Sharpshooter
           drawn before the stops (scatter-free stops on a Sharpshooter spin) at each strip set's chance, the
           guaranteed-win wild / fallback, the shared wild counts and multipliers with the step 6 presentation
           rebuild, and SHARPSHOOTER Ante's own content (1 in 5, 1-6 wilds, in-run placement, no rebuild).
           Event: sharpshooter.
           Verified: forced base Sharpshooter avg award 11.623x +/- 0.083 (spec 11.630) over 48,000 spins, 2.94 wilds
           shown (award step 1.59), every rebuild exact and in-run; SHARPSHOOTER Ante 286.5x +/- 2.4 (spec 286.8)
           over 64,000, share / avg / median by wild count matching the spec's section 7 table; whole reel-spin
           return vs engine.py: base 0.5475 +/- 0.0030 (0.5488), wild_ante 2.514 +/- 0.014 (2.502);
           parity:sdk 0 differences on 40,000 books. The Python rebuild costs ~0.1 s a Sharpshooter.
  Step 3 - Showdown (section 8) in the reel-spin modes: drawn before the reels at each mode's chance (base / WILD Ante /
           SHARPSHOOTER Ante 1 in 126, SHOWDOWN Ante 1 in 10.2), base modifier odds 70 / 27.5 / 2.5 and the base number
           tables (solved X5000 weight); VS bounty 10 + value at 75%, + 10 + n, X 10 x n, capped at 50,000x.
           Event: showdown.
           Verified: 3,000,000 draws against the exact outcome distribution built from the spec's tables (29
           outcomes, chi2 31.8 on 28 dof, p = 0.28; no unknown outcome, no pay mismatch; exact avg 22.14595x = spec);
           a forced X5000 book pays 5,000,000 with finalWin.maxWin; parity:sdk 0 differences on 40,000 books.
           (engine.showdown_outcomes reads config.py's unsolved X5000 weight 0.02; the spec's solved weight is
           0.6328 - the spec is what's ported.)
  Step 4 - natural free spins (sections 9-10): 3 / 4 / 5+ scatters on a paid reel spin trigger SHERIFF / POSSE /
           SHOWDOWN BONUS (10 / 15 / 20 spins, fs_<tier> strips, wild floor 0 / 5 / 10, the tier's Showdown chance,
           modifier odds and number table, the shared Sharpshooter at the strips' chance raised to the floor);
           retriggers +5 / +10 / +15, uncapped; guarantees met by redrawing the whole free-spins round; the round is
           emitted spin by spin and stops at the max win. No setTotalWin inside free spins (spec 14.6).
           Verified against spec section 12 (presentation off; it never changes an award), per tier: return
           52.34x +/- 0.54 (52.0), 190.06x +/- 1.48 (192.0), 430.61x +/- 1.41 (432.0); from reels 5.98 / 56.22 /
           62.93 (6.0 / 56.4 / 63.0); Showdowns 2.014 / 3.741 / 5.811 (2.01 / 3.74 / 5.81); spins 10.20 / 15.26 /
           20.31; medians 37.5 / 120 / 244 (38 / 120 / 246); kept on the first draw 0.842 / 0.716 / 0.999 (0.843 /
           0.715 / 0.999). Trigger odds per reel spin 1 in 249 / 6,081 / 376,241 (exact = spec). Base RTP assembled
           from the port's parts 95.89% (spec parts with the sampled reel-spin value 95.91%; the spec's own split gives
           0.5497 per reel spin -> 96.00%). parity:sdk 0 differences on 40,000 books.
  Step 5 - the buys: buy_sheriff 100x, buy_posse 300x, buy_showdown 500x play their bought bonus directly (bonusStart
           first; no trigger spin, no scatter pay) on fs_buy_<tier> with its own Showdown odds, Sharpshooter chance and
           guarantees (SHERIFF 2 Showdowns, POSSE a Showdown + a Sharpshooter, SHOWDOWN a Showdown). In every free-spins
           round the Sharpshooter presentation now runs only on the kept round (play_free_spins -> present_kept): it
           never changes an award, and rounds redrawn for their guarantees (POSSE buy keeps 28%) would waste it.
           Verified against spec section 12 (per buy): return 95.76x +/- 0.90 (96.0), 286.49x +/- 1.55 (288.0),
           477.80x +/- 1.85 (480.0); from reels 12.14 / 89.04 / 72.27 (12.2 / 88.9 / 72.3); Showdowns 2.628 / 3.669 /
           5.812 (2.63 / 3.67 / 5.81); spins 10.24 / 15.30 / 20.30; medians 55 / 168 / 278 (56 / 168 / 276); kept on the
           first draw 0.525 / 0.278 / 0.999 (0.524 / 0.277 / 0.999). parity:sdk 0 differences on 70,000 books (1,614
           buy retriggers). Debug run, all 7 modes at 10,000: ~2 minutes.
  Step 6a - the exact category model and the re-solve (published weights from the spec's exact probabilities, user
           decision 2026-09-30). targets.py splits every mode into categories with exact probabilities: each paid
           Showdown outcome; the Sharpshooter spin; the ordinary reel spin; per natural tier, each big X class of
           the free-spins round (the largest X >= 25 among its Showdowns, from an exact forward dynamic program over
           spins left / Showdowns / Sharpshooter seen with the guarantees conditioned on); buys: the big X classes
           of the bought round. Reel-spin line means and Sharpshooter awards come from large samples of the
           outline's vectorized engine (reference/, copied verbatim). The model put the frozen design at base
           95.86%, WILD Ante 96.39%, SHOWDOWN Ante 95.96%, SHARPSHOOTER Ante ~95.6%; resolve.py re-solved the four
           solved parameters (base and SHOWDOWN Ante Showdown rates in closed form, the WILD Ante ladder and
           SHARPSHOOTER Ante multiplier tilts by importance reweighting), averaged over two independent full-size
           solves (64M WILD Ante spins, 24M forced SHARPSHOOTER Ante Sharpshooters): base rate 0.0079878, SHOWDOWN
           Ante 0.0978900, WILD tilt 0.142186, SHARPSHOOTER tilt 1.466316 (user decision 2026-09-30; written into
           the outline's math_spec.json / .md, backup _backup_20260930, and the game repo's copy).
           Model on the final spec (targets.json): base 95.996%, wild_ante 95.927%, showdown_ante 95.999%,
           sharpshooter_ante 96.172% (its 2M-spin Sharpshooter sample is +/-0.14%), buys 95.998 / 96.006 / 95.968%.
           The bonus program reproduces the spec: EV 51.995 / 192.07 / 431.96 / 96.006 / 288.05 / 479.98, kept on
           the first draw 0.8425 / 0.7145 / 0.9989 / 0.5237 / 0.2781 / 0.9989, Showdowns and spins as section 12.
           Run: PYTHONPATH=. python3 games/sheriff_showdown/targets.py (~15 min), resolve.py (~20 min).
  Step 6b - books by category and the published weights. Every distribution is one category (categories.py, from
           targets.json) with a fixed number of books, generated inside it from the game's own distribution:
           a paid Showdown outcome (1 book each - its board and award are fixed); a Sharpshooter spin; an ordinary
           reel spin (redrawn while it shows 3+ scatters); a bonus of a given big X class - a paid spin's stops
           drawn among those showing exactly the tier's scatters (game_calculations.stops_with_scatters), or a
           buy - with the free-spins round played with its Showdowns' outcomes undrawn, redrawn for its
           guarantees, accepted with probability P(class | n Showdowns) / max and given outcomes from their exact
           conditional distribution (play_free_spins_class). Seeds differ by mode (modes sharing strips no longer
           repeat each other's books). weights.py replaces the optimizer: each category gets exactly its probability,
           and inside it the least change from equal weights (w ~ exp(lambda x payout)) that hits its target
           average; integer weights summing to 2^50. Each mode's remaining model gap to 96.00% goes into the
           categories whose averages are sample estimates (categories.ABSORB): base / SHOWDOWN Ante ordinary
           spins, WILD Ante ordinary spins + Sharpshooter, SHARPSHOOTER Ante Sharpshooter (target 286.83x, the
           re-solved award), the buys' "none" class.
           Verified at 10,000 books a mode: every published table 96.00000%; Showdown, X, Sharpshooter and natural
           trigger frequencies equal the exact model to every printed digit in all four paid modes; 50,000x 1 in
           3.68M base, 1 in 8,779 / 8,620 / 3,185 buys (spec 8,778 / 8,620 / 3,185); events per book 17.8 paid,
           30.9 / 45.1 / 57.2 buys (<= 5.7M a mode at 100,000 books, under Stake's 10M); parity:sdk 0 differences on
           70,000 books. Debug run ~9 minutes.
