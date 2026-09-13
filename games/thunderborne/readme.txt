# Thunderborne

3 reels x 5 rows, 15 paylines, 3-of-a-kind left to right. Pays are x base bet per line, lines summed.
WILD (W) substitutes for every symbol except BONUS (S). 3 BONUS symbols (one per reel) trigger free spins.
Max win 5000x in every mode; the round ends there.

Source of truth: the thunderborne-rebuild fake math (src/config/gameConfig.ts, src/rgs/fakeMath/).
Reel strips in reels/ are exported from it exactly. Symbol ids match the client: T = "10", N = "9".

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

Port status:
  Step 1 - grid, paytable, paylines, strips, bet modes; features off (line wins only, uniform board draws).
           Debug: PYTHONPATH=. python3 games/thunderborne/run_debug.py
  Later  - WILD STRIKE frame + strikes, free spins, buys, antes, optimizer criteria, event alignment.
