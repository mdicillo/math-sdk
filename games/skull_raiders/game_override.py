from game_executables import GameExecutables
from src.calculations.statistics import get_random_outcome
from src.events.events import fs_trigger_event


class GameStateOverride(GameExecutables):
    """
    This class is is used to override or extend universal state.py functions.
    e.g: A specific game may have custom book properties to reset
    """

    def reset_book(self):
        super().reset_book()
        # Per-round feature state: the tier + the reel the free spins draw from. Cleared each round so a
        # stale tier/reel can't leak from a previous simulation.
        self.fs_tier = None
        self.fs_feature_reel = None

    def assign_special_sym_function(self):
        self.special_symbol_functions = {
            "W": [self.assign_mult_property],
        }

    def assign_mult_property(self, symbol) -> dict:
        """Assign a multiplier to each WILD, rolled from the active mode's per-gametype bag.

        Unlike the reference lines game (feature-only), Skull Raiders has multiplier wilds in BASE too:
        a tame bag in the base game, a fat bag in free spins. Only >=2 wilds contribute to a line (the
        "symbol" strategy sums them); a x1 wild carries no badge and adds nothing. gameConfig.ts:174-194.
        """
        mult_values = self.get_current_distribution_conditions()["mult_values"]
        bag = mult_values.get(self.gametype)
        multiplier_value = get_random_outcome(bag) if bag else 1
        symbol.assign_attribute({"multiplier": multiplier_value})

    def update_freespin(self):
        """Annotate each free-spin's updateFreeSpin with the running round win, so the client's
        book-player shows the same live feature total the fake-math path does (byte-identical replay)."""
        super().update_freespin()
        self.book.events[-1]["totalWin"] = round(self.win_manager.running_bet_win * 100)

    def update_freespin_amount(self, scatter_key: str = "scatter"):
        """Set the feature TIER, initial spins and per-tier reel at the trigger.

        Tier is fixed by scatter count: 3/4/5 -> tier 1/2/3 (8/12/15 spins). A NATURAL trigger (base game
        or an ante — not a buy) clamps to naturalMaxTier=2, so it can never award HIDDEN even on 5
        scatters; a BUY runs exactly the forced tier (Mystery can roll tier 3). The feature reel follows
        (tier, is_buy): tier 3 -> FR3; bought tier 1/2 -> FRB; natural tier 1/2 -> FR0. Retriggers add
        spins but never change the tier or reel. gameConfig.ts: naturalMaxTier / selectBonusLevel.
        """
        is_buy = self.get_current_betmode().get_buybonus()
        count = self.count_special_symbols(scatter_key)
        if not is_buy:
            count = min(count, self.config.natural_max_tier + 2)  # clamp natural to tier <= naturalMaxTier
        count = max(3, min(5, count))
        self.fs_tier = count - 2  # 3->1, 4->2, 5->3

        if self.fs_tier >= 3:
            self.fs_feature_reel = self.config.tier3_reel
        elif is_buy:
            self.fs_feature_reel = self.config.buy_reel
        else:
            self.fs_feature_reel = self.config.natural_reel

        # Size the award from the (clamped/forced) count and emit the enriched trigger event. Not via
        # super(), which would re-read the raw count and skip the tier clamp.
        self.tot_fs = self.config.freespin_triggers[self.gametype][count]
        basegame_trigger = self.gametype == self.config.basegame_type
        fs_trigger_event(self, basegame_trigger=basegame_trigger, freegame_trigger=not basegame_trigger)
        ev = self.book.events[-1]
        ev["level"] = int(self.fs_tier)
        ev["count"] = int(count)

    def update_fs_retrigger_amt(self, scatter_key: str = "scatter"):
        """Retrigger adds the landed tier's spins, capped so total spins never exceed bonus_max (30).

        Once capped, further scatters add nothing (the BONUS is spent). The tier/reel are unchanged.
        gameConfig.ts: bonusMax / generateBonus retrigger.
        """
        if self.tot_fs >= self.config.bonus_max:
            return
        count = max(3, min(5, self.count_special_symbols(scatter_key)))
        add = min(
            self.config.freespin_triggers[self.config.freegame_type][count],
            self.config.bonus_max - self.tot_fs,
        )
        if add <= 0:
            return
        self.tot_fs += add
        fs_trigger_event(self, freegame_trigger=True, basegame_trigger=False)
        ev = self.book.events[-1]
        ev["level"] = int(self.fs_tier)
        ev["added"] = int(add)
        ev["capped"] = self.tot_fs >= self.config.bonus_max

    def get_current_distribution_conditions(self) -> dict:
        """Point the free-spin board draws at this feature's tier reel (fs_feature_reel).

        Returns a shallow copy with reel_weights[freegame] repointed, so the tier a feature runs — rolled
        naturally or bought — selects its pool. Copy, never mutate: the conditions dict is shared config
        read across sim threads.
        """
        cond = super().get_current_distribution_conditions()
        if self.gametype == self.config.freegame_type and isinstance(cond, dict):
            # The wincap criteria forces the max-win tail on the WILD-rich WCAP pool; every other feature
            # runs on its tier reel (fs_feature_reel).
            reel = "WCAP" if self.criteria == "wincap" else getattr(self, "fs_feature_reel", None)
            if reel:
                cond = dict(cond)
                rw = dict(cond.get("reel_weights", {}))
                rw[self.config.freegame_type] = {reel: 1}
                cond["reel_weights"] = rw
        return cond

    def check_repeat(self):
        super().check_repeat()
        if self.repeat is False:
            win_criteria = self.get_current_betmode_distributions().get_win_criteria()
            if win_criteria is not None and self.final_win != win_criteria:
                self.repeat = True
                return
            if win_criteria is None and self.final_win == 0:
                self.repeat = True
                return
