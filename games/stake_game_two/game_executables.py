from game_calculations import GameCalculations
from src.calculations.ways import Ways
from src.calculations.statistics import get_random_outcome


class GameExecutables(GameCalculations):
    """Ways + cascade (tumble) executables.

    The cascade reuses the SDK's Tumble machinery (Executables.tumble_game_board /
    emit_tumble_win_events / evaluate_wincap). This class adds the ways evaluation and, crucially,
    marks the winning symbols so the tumble removes them.
    """

    def get_ways_update_wins(self):
        """Evaluate the current board for ways wins, add WILD's flat pay, flag winning symbols for the
        tumble, and update the win manager. The ladder is applied as a GLOBAL multiplier
        (self.global_multiplier), which the caller climbs by +1 per winning tumble.

        spin_win accumulates across the whole cascade (update_spinwin ADDS), so each tumble's win adds
        to the sequence total — exactly the cascade behaviour.
        """
        self.win_data = Ways.get_ways_data(
            self.config,
            self.board,
            global_multiplier=self.global_multiplier,
            multiplier_strategy="global",
        )
        # WILD flat pay (Milestone B): stacks on top of the ways wins the same wilds complete.
        self.add_wild_pay()
        # Flag every winning cell (including the wilds that completed a win) so tumble_board removes
        # them on the next gravity step. Scatters and an inert "?" never win, so they are never flagged
        # — matching "SCATTER never tumbles".
        for win in self.win_data["wins"]:
            for pos in win["positions"]:
                self.board[pos["reel"]][pos["row"]].explode = True

        if self.win_data["totalWin"] > 0:
            Ways.record_ways_wins(self)
            self.win_manager.update_spinwin(self.win_data["totalWin"])
        self.win_manager.tumble_win = self.win_data["totalWin"]

    def add_wild_pay(self):
        """WILD's own pay: a flat `config.wild_pay` (x total bet) awarded ONCE when a wild sits on ALL
        five reels, multiplied by the current ladder (global_multiplier) but NOT by the ways count.
        Appended to win_data as a distinct win so it flows through recording/emission like any other,
        and stacks on top of the symbol wins those wilds complete. Mirrors evaluateWildPay in ways.ts.

        No-op unless every reel carries a wild. All wild cells are listed as positions so they are
        removed by the tumble (they participated in the win)."""
        wild = self.config.special_symbols["wild"][0]
        per_reel_cells = []
        for reel in range(self.config.num_reels):
            cells = [
                {"reel": reel, "row": row}
                for row in range(len(self.board[reel]))
                if self.board[reel][row].name == wild
            ]
            if not cells:
                return  # wild missing on a reel → no flat wild pay
            per_reel_cells.append(cells)

        positions = [c for cells in per_reel_cells for c in cells]
        base = self.config.wild_pay
        win = round(base * self.global_multiplier, 2)
        self.win_data["wins"].append(
            {
                "symbol": wild,
                "kind": self.config.num_reels,
                "win": win,
                "positions": positions,
                "meta": {
                    "ways": 1,
                    "globalMult": self.global_multiplier,
                    "winWithoutMult": base,
                    "symbolMult": 0,
                    "wildPay": True,
                },
            }
        )
        self.win_data["totalWin"] = round(self.win_data["totalWin"] + win, 2)

    # --- Mystery "?" wheel (Milestone C) --------------------------------------------------------
    def evaluate_drop(self, always_activate: bool):
        """Evaluate one drop of a cascade, with the mystery wheel folded in at the LOCKED ordering
        (docs/WHEEL_TIMING.md): each "?" spins the wheel FIRST — boosting the ladder — then the win
        pays at the boosted ladder. The +1 per-tumble increment happens between drops (the caller).

        `always_activate` is False in the base game (a "?" activates only on a drop that pays) and True
        in free spins (a "?" always spins, even on a non-winning terminal drop, where its boost can
        raise a ladder that persists into the next spin). Multiple "?" on one board each roll and
        STACK (spin_board_wheels reads the running multiplier).
        """
        if self._wheel_enabled():
            if always_activate or self._board_has_win():
                self.spin_board_wheels()
        # Evaluate + record at the (now boosted) ladder, add the WILD flat pay, flag winners to tumble.
        self.get_ways_update_wins()

    def _wheel_enabled(self) -> bool:
        return bool(getattr(self.config, "wheel_results", None)) and getattr(self.config, "mystery_symbol", None)

    def _wild_on_all_reels(self) -> bool:
        wild = self.config.special_symbols["wild"][0]
        return all(
            any(self.board[r][row].name == wild for row in range(len(self.board[r])))
            for r in range(self.config.num_reels)
        )

    def _board_has_win(self) -> bool:
        """Does the current board pay anything (ways win or the flat WILD pay)? Probes at 1x — the
        existence of a win is independent of the ladder. Used only for the base-game activation gate."""
        probe = Ways.get_ways_data(self.config, self.board, global_multiplier=1, multiplier_strategy="global")
        return probe["totalWin"] > 0 or self._wild_on_all_reels()

    def roll_wheel(self) -> dict:
        """Roll one wheel result from wheel_results. In an `untilUpgrade` free round the +5 ADD slot is
        swapped for the Upgrade (persistence flip, no boost) until an upgrade is spent, after which it
        reverts to +5 (Stage 8). Mirrors toUpgradeSlot + the provider's upgrade-then-plain roller."""
        results = self.config.wheel_results
        idx = int(get_random_outcome({i: r["weight"] for i, r in enumerate(results)}))
        slot = dict(results[idx])
        wants_upgrade = (
            self.gametype == self.config.freegame_type
            and getattr(self, "fs_persistence", "persistent") == "untilUpgrade"
            and not getattr(self, "upgrade_spent", False)
        )
        if wants_upgrade and slot["kind"] == "add" and slot["value"] == 5:
            slot = {"kind": "upgrade", "value": 0}
        return slot

    def apply_wheel(self, multiplier: int, slot: dict) -> int:
        """Apply a wheel slot to the ladder: 'add' bumps by value, 'mult' multiplies, 'upgrade' leaves
        it unchanged (its effect is the persistence flip, handled by the caller)."""
        if slot["kind"] == "add":
            return multiplier + slot["value"]
        if slot["kind"] == "mult":
            return multiplier * slot["value"]
        return multiplier  # 'upgrade'

    def spin_board_wheels(self) -> None:
        """Spin the wheel once for every "?" on the board, in reel-row order, each STACKING on the
        previous (it reads the running self.global_multiplier). Each "?" is consumed — flagged to
        tumble away so it cannot spin again. An Upgrade flips the feature to persistent."""
        mystery = self.config.mystery_symbol
        for reel in range(self.config.num_reels):
            for row in range(len(self.board[reel])):
                if self.board[reel][row].name != mystery:
                    continue
                slot = self.roll_wheel()
                frm = self.global_multiplier
                self.global_multiplier = self.apply_wheel(frm, slot)
                if slot["kind"] == "upgrade":
                    self.fs_persistent = True
                    self.upgrade_spent = True
                self.board[reel][row].explode = True  # consumed
                self._emit_wheel_spin(reel, row, slot, frm, self.global_multiplier)

    def run_opening_wheels(self) -> None:
        """Free wheel spins at feature entry (tier 3's opening roll). Cell-less (reel=-1). Boosts the
        carried feature ladder before spin 1; on a persistent tier that boost carries the whole run."""
        for _ in range(int(getattr(self, "fs_opening_wheel_spins", 0))):
            slot = self.roll_wheel()
            frm = self.feature_ladder
            self.feature_ladder = self.apply_wheel(frm, slot)
            if slot["kind"] == "upgrade":
                self.fs_persistent = True
                self.upgrade_spent = True
            self._emit_wheel_spin(-1, -1, slot, frm, self.feature_ladder)

    def _emit_wheel_spin(self, reel: int, row: int, slot: dict, frm: int, to: int) -> None:
        """Custom book event: one "?" activation. Informational for the client; the RTP-bearing effect
        is already in the boosted ladder that the following win pays at."""
        self.book.add_event(
            {
                "index": len(self.book.events),
                "type": "wheelSpin",
                "cell": {"reel": reel, "row": row},
                "result": slot,
                "from": frm,
                "to": to,
            }
        )
