"""Sheriff Showdown game state: plays one round per simulation and writes its book (the client's
src/rgs/sheriff/provider.ts round() + BookBuilder)."""

from src.state.state import GeneralGameState

import spec
from game_calculations import play_free_spins, play_spin
from game_events import (
    bonus_end_event,
    bonus_retrigger_event,
    bonus_start_event,
    bonus_trigger_event,
    bonus_update_event,
    final_win_event,
    reveal_event,
    set_total_win_event,
    sharpshooter_event,
    showdown_event,
    to_units,
    win_info_event,
)


class GameState(GeneralGameState):
    """Handles game logic and events for a single simulation number/game-round."""

    def assign_special_sym_function(self):
        # The game's boards are plain symbol ids (game_calculations.py); the SDK's symbol objects aren't used.
        self.special_symbol_functions = {}

    def reset_book(self):
        super().reset_book()
        # The round's running total in book units, clamped at the max win (WINCAP_X x 100).
        self.total_units = 0
        self.cap_units = to_units(spec.WINCAP_X)

    @property
    def capped(self) -> bool:
        return self.total_units >= self.cap_units

    def pay(self, units: int) -> int:
        """Add an award to the round, clamped to the max win. Returns the amount actually paid (book units)."""
        paid = min(units, max(0, self.cap_units - self.total_units))
        self.total_units += paid
        self.win_manager.update_spinwin(paid / 100)
        return paid

    def run_spin(self, sim, simulation_seed=None):
        self.reset_seed(sim)
        self.repeat = True
        while self.repeat:
            self.reset_book()
            if self.betmode in spec.BUY_MODES:
                # A buy plays its bonus directly: no trigger spin, no scatter pay.
                self.free_spins(spec.BUY_MODES[self.betmode]["free_spins"])
                self.update_final_win()
                final_win_event(self, self.total_units, self.capped)
                self.check_repeat()
                continue
            mode = spec.BASE_MODES[self.betmode]
            result = play_spin(mode["showdown"], mode["strips"], 0, mode.get("wild_multipliers"), mode.get("sharpshooter"))
            if result["kind"] == "showdown":
                self.showdown(result["showdown"])
                set_total_win_event(self, self.total_units)
                self.win_manager.update_gametype_wins(self.gametype)
            else:
                self.reel_spin(result)
                if self.total_units > 0:
                    set_total_win_event(self, self.total_units)
                self.win_manager.update_gametype_wins(self.gametype)
                natural = spec.natural_mode_for(result["scatter"]["count"])
                if natural and not self.capped:
                    self.record({"bonus": natural["id"], "gametype": self.gametype})
                    bonus_trigger_event(self, result["scatter"], natural)
                    self.free_spins(natural)

            self.update_final_win()
            final_win_event(self, self.total_units, self.capped)
            self.check_repeat()
        self.imprint_wins()

    def showdown(self, sd: dict) -> int:
        """One Showdown spin's event; its award (clamped at the max win) is the spin's pay."""
        self.win_manager.reset_spin_win()
        paid = self.pay(to_units(sd["awardX"]))
        self.record({"showdown": sd["modifier"], "gametype": self.gametype})
        showdown_event(self, sd, paid)
        return paid

    def reel_spin(self, result: dict) -> int:
        """One normal reel spin's events: reveal, then winInfo with what the spin added to the round."""
        self.win_manager.reset_spin_win()
        reveal_event(self, result)
        if result["sharpshooter"]:
            self.record({"sharpshooter": len(result["sharpshooter"]["wilds"]), "gametype": self.gametype})
            sharpshooter_event(self, result["sharpshooter"])
        total = to_units(result["scatter"]["payX"]) + sum(to_units(line["payX"]) for line in result["lines"])
        paid = self.pay(total)
        win_info_event(self, result, paid)
        return paid

    def free_spins(self, mode: dict) -> None:
        """One free-spins round (natural or bought). The round is drawn whole - redrawn until it meets its guarantees -
        then emitted spin by spin, stopping at the max win (provider.ts BookBuilder.freeSpins)."""
        round_ = play_free_spins(mode)
        self.triggered_freegame = True
        self.gametype = self.config.freegame_type
        bonus_start_event(self, mode)
        remaining = awarded = mode["spins"]
        feature_win = 0
        for spin in round_["spins"]:
            remaining -= 1
            result = spin["result"]
            feature_win += self.showdown(result["showdown"]) if result["kind"] == "showdown" else self.reel_spin(result)
            self.win_manager.update_gametype_wins(self.gametype)
            if self.capped:
                remaining = 0
            elif spin["added"] > 0:
                awarded += spin["added"]
                remaining += spin["added"]
                capped = spec.RETRIGGER_CAP is not None and awarded >= spec.RETRIGGER_CAP
                bonus_retrigger_event(self, spin["added"], awarded, remaining, capped)
            bonus_update_event(self, remaining, awarded, feature_win)
            if self.capped:
                break
        bonus_end_event(self, mode, feature_win, self.capped)
        self.gametype = self.config.basegame_type

    def run_freespin(self):
        """Free spins run inside run_spin (free_spins): the round is drawn whole before its events are written."""
        raise NotImplementedError
