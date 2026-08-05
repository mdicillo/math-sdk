# Stake Game Two — 5x3, 243-ways cascading (tumble) slot

Stake Engine math-SDK port of the TS fake-math model in the stake-game-two repo (working title
"Jelly Jamboree"). It deliberately mimics the live Rage Quit (Meta Gaming) title.

Model summary (authoritative spec: docs/CASCADE_MYSTERY_REWORK.md in the game repo):
- 5x3, 243 ways, left-to-right, min 3 reels. Cascading tumble in BOTH base and free spins: winning
  symbols are removed, survivors fall, fresh symbols drop in, repeat until a drop pays nothing.
- Running win-multiplier LADDER: +1 per winning tumble. Base resets each spin; in free spins it
  persists across the whole feature (tier rules).
- Mystery "?" (M) wheel: on a winning tumble a "?" rolls a weighted wheel (+5/+10/+20/+50/+100/x2,
  and Upgrade in a 3-scatter round) and boosts the ladder BEFORE that drop pays, then is consumed.
  Base game: activates only on a winning drop. Free spins: always.
- WILD (W): substitutes; its own pay is a flat 5x on all five reels, once, x the ladder, and it
  stacks on the symbol wins those wilds complete. Never a per-way pay.
- SCATTER (S): never tumbles, never pays; the final count is the tier. 3/4/5 -> tier 1/2/3.
- Three free-spins tiers: t1 (3sc, 10 spins, ladder resets until the wheel's Upgrade lands),
  t2 (4sc, 10 spins, persistent), t3 (5sc, 12 spins, persistent, +1 opening wheel spin). Retrigger
  awards a flat +5 spins. RTP 96.70%, max win 25,000x.
- Six bet modes: base, 3X Chance (3x/spin fee), Mystery Chance (50x/spin stake), Bonus (100x, 3sc),
  Super Bonus (200x, 4sc), Mystery Bonus (500x, rolls 45/45/10 across the tiers).

PORT MILESTONES (incremental, like camp_deadwater):
  A (built): base ways + cascade, units verified; ladder neutralized, wheel inert, base mode only.
  B: +1-per-tumble ladder + WILD flat 5x pay.
  C: "?" wheel + tiers + persistence + retrigger + tier-3 opening spin.
  D: six bet modes + optimizer + full cert run; lock certified MODE_RTP.

Reels: exported from the TS model (npm run reels:export in the game repo), renamed WILD->W,
SCATTER->S, MYSTERY->M. BR0 = base (carries symbolDensity shaping); FR0 = shared feature pool;
FR1/FR3 = per-tier feature pools (tier 2 shares FR0).

Runs:
  python games/stake_game_two/run_debug.py   # sims only, uncompressed, no Rust (units/math checks)
  make run GAME=stake_game_two               # full pipeline (sims + optimizer + analysis + checks)
