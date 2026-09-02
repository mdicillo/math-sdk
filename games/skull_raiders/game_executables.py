import random

from game_calculations import GameCalculations
from src.calculations.lines import Lines
from src.calculations.statistics import get_random_outcome
from src.events.events import reveal_event, set_total_event
from game_events import wheel_spin_event, wheel_convert_event, wheel_steal_event

LOWS = ["L1", "L2", "L3", "L4", "L5"]


class GameExecutables(GameCalculations):

    def evaluate_lines_board(self):
        """Populate win-data, record wins, transmit events."""
        self.win_data = Lines.get_lines(self.board, self.config, global_multiplier=self.global_multiplier)
        Lines.record_lines_wins(self)
        self.win_manager.update_spinwin(self.win_data["totalWin"])
        Lines.emit_linewin_events(self)

    # --- Raid wheel (custom base-game event) --------------------------------------------------------
    def run_wheel_round(self):
        """A base-spin wheel event replaces the normal line spin: draw a plain land, then ATTACK (redraw
        whole paylines) or STEAL (sweep every 3+ group) builds the entire win. gameConfig.ts wheel.
        """
        self.draw_board(emit_event=False)  # land, no reveal yet
        self._strip_specials()  # scatters + natural wilds -> random lows (the wheel makes the win)
        mode = "attack" if random.random() < self.config.wheel_attack_share else "steal"
        # Tag the sim so the optimizer can bucket wheel rounds into the "wheel" criteria
        # (search_conditions={"symbol": "wheel"}); force_info.md — record() drives force_record_<mode>.json.
        self.record({"symbol": "wheel", "kind": mode, "gametype": self.gametype})
        if mode == "attack":
            self._break_line_wins()  # land pays nothing; only the redrawn lines pay
            reveal_event(self)
            wheel_spin_event(self, "attack")
            self._run_attack()
        else:
            self._plant_steal()  # present symbol + banked wilds
            reveal_event(self)  # the composed steal board
            wheel_spin_event(self, "steal")
            self._score_steal()

    def _strip_specials(self):
        """Replace every scatter and natural wild with a random low, so the land carries no scatter and
        no natural wild (the wheel supplies its own wilds). Mirrors the TS excludeBonus land draw."""
        wild = self.config.special_symbols["wild"][0]
        scatter = self.config.special_symbols["scatter"][0]
        for reel in range(self.config.num_reels):
            for row in range(len(self.board[reel])):
                if self.board[reel][row].name in (wild, scatter):
                    self.board[reel][row] = self.create_symbol(random.choice(LOWS))
        self.get_special_symbols_on_board()

    def _break_line_wins(self):
        """ATTACK only: mutate the land until it has no line win, so the redrawn lines are the only pay.
        Breaks each winning line at reel 1; a bounded fallback guarantees termination."""
        for _ in range(30):
            wd = Lines.get_lines(self.board, self.config)
            if wd["totalWin"] == 0:
                return
            for w in wd["wins"]:
                line = self.config.paylines[w["meta"]["lineIndex"]]
                r0 = self.board[0][line[0]].name
                for cand in LOWS:
                    if cand != r0:
                        self.board[1][line[1]] = self.create_symbol(cand)
                        break
        # Fallback: give each reel a distinct low so no payline has two adjacent matches -> no win.
        for reel in range(self.config.num_reels):
            sym = LOWS[reel % len(LOWS)]
            for row in range(len(self.board[reel])):
                self.board[reel][row] = self.create_symbol(sym)

    def _run_attack(self):
        """Fireballs redraw whole paylines onto the (broken) land. For each of N chosen lines: a payout
        symbol T fills the line, with w wilds (each rolling a wheel multiplier) scattered along it. The
        board is then scored as ordinary line wins — one reel-0 conversion completes every payline
        through it, which is where ATTACK's richness comes from."""
        num_lines = int(get_random_outcome(self.config.attack_line_weights))
        num_lines = max(1, min(num_lines, len(self.config.paylines)))
        line_ids = random.sample(list(self.config.paylines.keys()), num_lines)

        cells = {}  # (reel,row) -> {name, multiplier}
        for lid in line_ids:
            line = self.config.paylines[lid]
            payout_sym = get_random_outcome(self.config.attack_symbol_weights)
            w = min(int(get_random_outcome(self.config.attack_extras_weights)), self.config.num_reels)
            wild_reels = set(random.sample(range(self.config.num_reels), w))
            for reel in range(self.config.num_reels):
                row = line[reel]
                if reel in wild_reels:
                    self._place_cell(cells, reel, row, self.config.special_symbols["wild"][0], self.config.attack_mult_bag)
                else:
                    self._place_cell(cells, reel, row, payout_sym, None)

        self.get_special_symbols_on_board()
        # Guarantee a win: if the conversions somehow paid nothing, force the first line to full wilds.
        if Lines.get_lines(self.board, self.config)["totalWin"] == 0:
            line = self.config.paylines[line_ids[0]]
            for reel in range(self.config.num_reels):
                self._place_cell(cells, reel, line[reel], self.config.special_symbols["wild"][0], self.config.attack_mult_bag)
            self.get_special_symbols_on_board()

        wheel_convert_event(
            self,
            [{"reel": r, "row": row, "name": v["name"], "multiplier": v["multiplier"]} for (r, row), v in cells.items()],
        )
        self.evaluate_lines_board()

    def _place_cell(self, cells, reel, row, name, mult_bag):
        """Write a symbol to the board (rolling a wheel multiplier for a wild) and record the change."""
        sym = self.create_symbol(name)
        mult = int(get_random_outcome(mult_bag)) if mult_bag else 1
        if mult_bag:
            sym.assign_attribute({"multiplier": mult})
        self.board[reel][row] = sym
        cells[(reel, row)] = {"name": name, "multiplier": mult}

    def _plant_steal(self):
        """Plant `present_n` copies of a present symbol and `k` banked multiplier wilds on the land. The
        rest of the board stays as neutralized lows; STEAL sweeps EVERY 3+ group, so background low
        groups can bank too (faithful to evaluateSteal)."""
        present_sym = get_random_outcome(self.config.steal_present_weights)
        min_match = min(k for (k, _s) in self.config.paytable.keys())
        num_cells = sum(len(self.board[r]) for r in range(self.config.num_reels))
        present_n = max(min_match, min(int(get_random_outcome(self.config.steal_present_count_weights)), num_cells))
        k = int(get_random_outcome(self.config.steal_wild_count_weights))

        all_cells = [(r, row) for r in range(self.config.num_reels) for row in range(len(self.board[r]))]
        random.shuffle(all_cells)
        present_cells = all_cells[:present_n]
        wild_cells = all_cells[present_n : present_n + k]
        for (r, row) in present_cells:
            self.board[r][row] = self.create_symbol(present_sym)
        for (r, row) in wild_cells:
            sym = self.create_symbol(self.config.special_symbols["wild"][0])
            sym.assign_attribute({"multiplier": int(get_random_outcome(self.config.steal_mult_bag))})
            self.board[r][row] = sym
        self.get_special_symbols_on_board()
        self._steal_present_sym = present_sym
        self._steal_present_cells = [{"reel": r, "row": row} for (r, row) in present_cells]

    def _score_steal(self):
        """Score the composed steal board (position-agnostic) and emit the wheel + total-win events.

        A STEAL pays via the wheelSteal event (every 3+ group x the summed wild factor), NOT via lines —
        so it emits reveal / wheelSpin / wheelSteal / setTotalWin / finalWin and NO winInfo. Emitting a
        winInfo here (as an earlier version did) makes the client run the ordinary line-win presentation
        over the steal, which lights only the group cells and leaves the multiplier WILDs blacked out.
        Mirrors the fake-math STEAL event stream exactly (provider.ts generateWheelRound).
        """
        wd = self.evaluate_steal(self.board, self.config)
        self.win_data = wd
        self.win_manager.update_spinwin(wd["totalWin"])
        factor = wd["wins"][0]["meta"]["multiplier"] if wd["wins"] else 1
        wheel_steal_event(
            self,
            self._steal_present_sym,
            wd["positions"],  # every stolen cell (all group members + wild coins), not just the present symbol
            wd["totalWin"],
            factor,
            [{"symbol": w["symbol"], "count": w["kind"], "win": int(round(w["win"] * 100, 0))} for w in wd["wins"]],
        )
        if wd["totalWin"] > 0:
            self.evaluate_wincap()
            set_total_event(self)
