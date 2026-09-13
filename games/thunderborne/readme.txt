# Thunderborne

3 reels x 5 rows, 15 paylines, 3-of-a-kind left to right. Pays are x base bet per line, lines summed.
WILD (W) substitutes for every symbol except BONUS (S). 3 BONUS symbols (one per reel) trigger free spins.
Max win 5000x in every mode; the round ends there.

WILD STRIKE: every spin a frame settles on one cell. When a WILD lands in it, every WILD on the board beams to Thor,
and the more beam, the likelier WILD STRIKE: new wilds with 3x-10x multipliers strike open cells (neither WILD nor
BONUS). On a line, the multipliers of its WILDs are added together. Every strike's spin pays at least 5x and at
most the base-game ceiling (2500x; 5000x with WILD BOOST on). Naturally landed base-game WILDs are 1x.

Source of truth: the thunderborne-rebuild fake math (src/config/gameConfig.ts, src/rgs/fakeMath/).
Reel strips in reels/ are exported from it exactly. Symbol ids match the client: T = "10", N = "9".
Parity: in thunderborne-rebuild, `npm run parity` checks this game's debug books against the fake math.

Bet modes:
  base                             1x
  base_wild_boost                  3x   WILD BOOST ante (more WILDs, stronger WILD STRIKE)
  base_activate_wheel              3x   ACTIVATE WHEEL ante (more triggers, every natural trigger plays the wheel)
  base_wild_boost_activate_wheel   6x   both antes
  bonus                            100x BONUS buy: 10 free spins, WILDs 2x
  super_bonus                      300x SUPER BONUS buy: 20 free spins, WILDs 3x
  wheel_bonus                      150x WHEEL BONUS buy: the wheel, then 10 free spins at its multiplier
All modes target 96% RTP.

Reels:
  BR0      base game               (gameConfig.ts BASE_STRIP)
  BR_WB    WILD BOOST base game    (ANTE_STRIPS.wild_boost)
  BR_AW    ACTIVATE WHEEL base game (ANTE_STRIPS.wheel_ante, 400 cells)
  BR_WBAW  both antes base game    (ANTE_STRIPS.both)
  FR0      every free-spin feature (FREE_STRIP)

Custom events (rows count the padding row, as winInfo's positions do):
  wildFrame   {cell: {reel, row}, beams: [{reel, row}]}   after every reveal
  wildStrike  {wilds: [{reel, row, mult}]}                 after wildFrame, before winInfo

Port status:
  Step 1 - grid, paytable, paylines, strips, bet modes (line wins only, uniform board draws).
  Step 2 - base-game WILD STRIKE: the frame, beams, aimed strikes (BASE_STRIKE; BOOST_STRIKE with WILD BOOST).
           Free spins still off.
           Debug: PYTHONPATH=. python3 games/thunderborne/run_debug.py
  Later  - free spins, buys, ante features, optimizer criteria, event alignment.
