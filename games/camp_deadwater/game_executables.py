import random

from game_calculations import GameCalculations
from src.calculations.lines import Lines
from src.calculations.statistics import get_random_outcome
from src.events.events import json_ready_sym


class GameExecutables(GameCalculations):

    def roll_merit_badge(self) -> int:
        """This spin's merit badge, rolled from the current distribution's mult_values for this gametype.
        Live in BOTH base and free games. Rolled ONCE per spin and stored as self.spin_badge (see
        gamestate) so a Helping Hands spin's natural and tumbled boards share the same badge. In free
        spins the tier FLOOR applies: badge = max(roll, tier_floor[tier]) — tiers 2/3 light >= 3× / 5×."""
        dist = self.get_current_distribution_conditions()["mult_values"][self.gametype]
        badge = get_random_outcome(dist)
        if self.gametype == self.config.freegame_type:
            badge = max(badge, self.config.tier_floor.get(getattr(self, "fs_tier", 1), 1))
        return badge

    def evaluate_lines_board(self):
        """Score the current board, record wins, transmit events.

        Merit badge (matches applyWildMultiplier in the TS model): self.spin_badge multiplies the WHOLE
        spin's win, but ONLY when a WILD is part of a winning line. We probe the board at 1× to detect the
        wild-in-win, then evaluate with the badge as a GLOBAL multiplier (applies to every line, so total
        × badge). A 1× badge (or no wild-in-win) leaves the win as-is. Called twice on a hands spin
        (natural, then tumbled) — spin_win accumulates, so the two wins are ADDED (additive feature)."""
        badge = getattr(self, "spin_badge", 1)
        probe = Lines.get_lines(self.board, self.config, global_multiplier=1)
        has_wild_win = any(
            self.board[p["reel"]][p["row"]].check_attribute("wild")
            for w in probe["wins"]
            for p in w["positions"]
        )
        self.global_multiplier = badge if (has_wild_win and badge > 1) else 1
        self.win_data = Lines.get_lines(
            self.board,
            self.config,
            multiplier_method="global",
            global_multiplier=self.global_multiplier,
        )
        Lines.record_lines_wins(self)
        self.win_manager.update_spinwin(self.win_data["totalWin"])
        Lines.emit_linewin_events(self)

    # --- Helping Hands (free-spins only) --------------------------------------------------------
    def _is_wild(self, sym) -> bool:
        return sym.check_attribute("wild")

    def _grab_symbol(self):
        """Draw one symbol from the wild-rich tumble-refill pool (grab_dist)."""
        return self.create_symbol(get_random_outcome(self.config.grab_dist))

    def maybe_run_hands(self) -> bool:
        """On a weighted trigger (free spins only), zombie hands clear non-wild cells strictly BELOW each
        reel's lowest wild; the reel tumbles down (all wilds preserved and slid toward the bottom) and the
        vacated top cells refill wild-rich. Mutates self.board and emits a handClear event. Returns True
        if it fired, so the caller re-scores the tumbled board (ADDED to the natural win). NEVER clears a
        wild: a reel's clearable region is only the cells below its lowest wild, and we clear from the
        bottom within that region."""
        if random.random() >= self.config.hands_trigger_chance:
            return False

        minh = self.config.hands_min_height
        # Per reel: number of bottom cells clearable (strictly below the lowest wild; all rows if no wild).
        clearable = []
        for reel in range(self.config.num_reels):
            col = self.board[reel]
            lowest_wild = max((r for r in range(len(col)) if self._is_wild(col[r])), default=-1)
            clearable.append(len(col) if lowest_wild < 0 else len(col) - 1 - lowest_wild)

        eligible = [r for r in range(self.config.num_reels) if clearable[r] >= minh]
        if not eligible:
            return False

        # Number of hands — capped by the tier's maxHands and the eligible-reel count.
        max_hands = min(self.config.hands_max_by_tier.get(getattr(self, "fs_tier", 1), 3), len(eligible))
        count_dist = {k: v for k, v in self.config.hands_count_weights.items() if k <= max_hands}
        n_hands = int(get_random_outcome(count_dist))
        reels = random.sample(eligible, n_hands)

        hands = []
        for reel in reels:
            height = int(get_random_outcome(self.config.hands_height_weights))
            k = min(height, clearable[reel])
            if k < minh:
                continue
            col = self.board[reel]
            rows_n = len(col)
            # Drop the bottom k (all non-wild), slide survivors down, refill k wild-rich cells at the top.
            self.board[reel] = [self._grab_symbol() for _ in range(k)] + col[0 : rows_n - k]
            hands.append({"reel": reel, "height": k})

        if not hands:
            return False

        self.get_special_symbols_on_board()
        self._emit_hand_clear(hands)
        return True

    def _emit_hand_clear(self, hands: list) -> None:
        """Custom event: the tumbled board + which reels/heights the hands worked. Client animates the grab."""
        special_attributes = list(self.config.special_symbols.keys())
        board_client = [
            [json_ready_sym(self.board[reel][row], special_attributes) for row in range(len(self.board[reel]))]
            for reel in range(len(self.board))
        ]
        self.book.add_event(
            {
                "index": len(self.book.events),
                "type": "handClear",
                "hands": hands,
                "board": board_client,
            }
        )
