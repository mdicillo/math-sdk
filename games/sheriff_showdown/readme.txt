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
