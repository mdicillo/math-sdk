# Thunderborne

3 reels x 5 rows, 15 paylines, 3-of-a-kind left to right. Pays are x base bet per line, lines summed.
WILD (W) substitutes for every symbol except BONUS (S). 3 BONUS symbols (one per reel) trigger free spins.
Max win 5000x in every mode; the round ends there.

WILD STRIKE: every spin a frame settles on one cell. When a WILD lands in it, every WILD on the board beams to Thor,
and the more beam, the likelier WILD STRIKE: new wilds with 3x-10x multipliers strike open cells (neither WILD nor
BONUS). On a line, the multipliers of its WILDs are added together. Every strike's spin pays at least 5x and at
most the base-game ceiling (2500x; 5000x with WILD BOOST on). Naturally landed base-game WILDs are 1x.

Free spins: 3 BONUS symbols award 10 free spins on the free-spin strip, naturally landed WILDs 2x. With ACTIVATE
WHEEL on, the wheel spins first and its multiplier (3x/4x/5x/7x/10x) replaces the 2x. Every free spin has the
frame and WILD STRIKE (free-spin chances), the feature's first strike is guaranteed, 3 BONUS symbols add 5 spins
up to 30, and a feature always pays at least 15x (its wins only, the triggering spin's win left out).

Buys: the base spin always lands the trigger (3 BONUS symbols on the base strips) and never beams, then the
feature plays by the same rules. BONUS: 10 spins, WILDs 2x. SUPER BONUS: 20 spins, WILDs 3x. WHEEL BONUS: the
wheel, then 10 spins at its multiplier. A bought feature pays at least 15% of its price (15x / 45x / 22.5x).

Source of truth: the thunderborne-rebuild fake math (src/config/gameConfig.ts, src/rgs/fakeMath/).
Reel strips in reels/ are exported from it exactly (FRWCAP is SDK-only, see below). Symbol ids match the client:
T = "10", N = "9". Parity: in thunderborne-rebuild, `npm run parity` checks this game's books against the fake math.

Bet modes:
  base                             1x
  base_wild_boost                  3x   WILD BOOST ante (more WILDs, stronger WILD STRIKE)
  base_activate_wheel              3x   ACTIVATE WHEEL ante (more triggers, every natural trigger plays the wheel)
  base_wild_boost_activate_wheel   6x   both antes
  bonus                            100x BONUS buy
  super_bonus                      300x SUPER BONUS buy
  wheel_bonus                      150x WHEEL BONUS buy
All modes target 96% RTP.

Reels:
  BR0      base game, and every buy's trigger spin (gameConfig.ts BASE_STRIP)
  BR_WB    WILD BOOST base game    (ANTE_STRIPS.wild_boost)
  BR_AW    ACTIVATE WHEEL base game (ANTE_STRIPS.wheel_ante, 400 cells)
  BR_WBAW  both antes base game    (ANTE_STRIPS.both)
  FR0      every free-spin feature (FREE_STRIP)
  FRWCAP   WILD-heavy free-spin strip for max-win books only (SDK only)

Criteria (the books' kinds; the optimizer sets how often each comes in the published game):
  wincap      the trigger forced and the feature played on FRWCAP with WINCAP_STRIKE until the round pays 5000x
  freegame    the trigger forced (buys: every other book)
  wildstrike  base-strip modes: played again until the base spin strikes (no trigger)
  basegame    base-strip modes: no trigger (a board showing 3 BONUS symbols is re-drawn)
Optimizer buckets (game_optimization.py), in order: wincap, freegame, wildstrike, 0, basegame (buys: wincap,
freegame). Targets are the fake math's measured split scaled to 96% and its max-win rates.

Deviations from the fake math:
  - A buy's trigger board is drawn like a natural trigger (force_special_board: a BONUS symbol at a random row of
    each reel's window on BR0); the fake math plants the three on the top row.
  - The fake math's BUY_WEIGHTING (keep one of several plays by total^lean) is not ported: bought features are
    simulated plainly and the optimizer re-weights them.
  - A feature under its floor or without a strike is always replayed; the fake math gives up after 50 replays.
  - Max-win books play their feature on FRWCAP with WINCAP_STRIKE (the fake math has no forced max wins).

Custom events (rows count the padding row, as winInfo's positions do):
  wildFrame   {cell: {reel, row}, beams: [{reel, row}]}   after every reveal
  wildStrike  {wilds: [{reel, row, mult}]}                 after wildFrame, before winInfo
  wheelSpin   {multiplier}                                 right before freeSpinTrigger (the wheel feature)
Standard events are the SDK's, except that a free spin that wins nothing sends no setTotalWin (the round's total hasn't
changed; game_executables.py evaluate_lines_board). At 100,000 books that keeps SUPER BONUS (~94 events a book) under
Stake's 10,000,000 events a mode; with it, ~108 a book came to ~10.8M. Base spins still always send it.

Running:
  PYTHONPATH=. python3 games/thunderborne/run.py         sims (compressed), optimizer, PAR sheet, format checks
  PYTHONPATH=. python3 games/thunderborne/run_debug.py   sims only, readable books, config files
run.py: 100,000 books a mode (certification, user go-ahead 2026-09-13). run_debug.py: 10,000 a mode (debug).

Port status:
  Step 1 - grid, paytable, paylines, strips, bet modes (line wins only).
  Step 2 - base-game WILD STRIKE: the frame, beams, aimed strikes (BASE_STRIKE; BOOST_STRIKE with WILD BOOST, WHEEL_STRIKE with ACTIVATE WHEEL, BOTH_STRIKE with
           both antes).
  Step 3 - natural free spins: FREE_STRIKE, the guaranteed strike, retriggers to 30, the 15x floor, the wheel.
  Step 4 - the buys: BONUS, SUPER BONUS, WHEEL BONUS.
  Step 5 - optimizer: wincap and wildstrike criteria, game_optimization.py, run.py (debug scale).
  Step 6 - the v3 base layout (2026-09-13): BR0 / BR_WB / BR_AW / BR_WBAW re-exported, BASE_STRIKE 0.13,
           BOOST_STRIKE 0.40 and BOTH_STRIKE (both antes) 0.39.
  Step 7 - v3 optimizer targets (BASE_TARGETS re-measured) and line-win scaling (x4 in 1-5x, base-strip modes).
  Step 8 - frame catches trimmed so the fake math plays 96% (BASE_STRIKE 0.12, WHEEL_STRIKE 0.14 for ACTIVATE
           WHEEL, BOTH_STRIKE 0.38) and those modes' BASE_TARGETS re-measured.
  Step 9 - line-win scaling split (x1.5 in 1-2x, x8 in 2-5x) and game_selection.py: run.py publishes each
           base-strip mode's optimizer candidate closest to the books' natural line-win spread.
  Step 10 - certification (2026-09-13): a free spin that wins nothing sends no setTotalWin (Stake's event limit),
            then run.py at 100,000 books a mode. game_selection.py caps every book at 1% of a base-strip table's weight
            (MAX_BOOK_SHARE): the optimizer weights each distinct payout and splits it among its books, so at 100,000
            books WILD BOOST's only 1.2x book came up 1 round in 31. The excess moves to the payouts either side in the
            same bucket, keeping each bucket's weight and average win. At 100,000 books the published line-win spread
            is 25-44 from natural (6-14 at 10,000); scaling trials didn't close it, and the user kept the certified
            tables with the cap.
  Later  - tuning against the PAR sheet.
