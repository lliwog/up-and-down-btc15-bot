from __future__ import annotations

from typing import TYPE_CHECKING

from bot.config import BotConfig
from bot.engine.pnl_tracker import PnLTracker
from bot.models.strategy_state import StrategyPhase, StrategySnapshot
from bot.models.ta_signal import TASignal
from bot.order_tracker.interface import OrderTracker
from bot.strategies.base import BaseStrategy
from bot.strategies.early_entry import EarlyEntryStrategy
from bot.strategies.late_scalp import LateScalpStrategy
from bot.strategies.mid_game import MidGameStrategy

if TYPE_CHECKING:
    from bot.db_events import DbEventCollector


class StrategyEngine:
    """Orchestrates strategies: mutual exclusion, priority-based entry, expiry."""

    def __init__(self, config: BotConfig, tracker: OrderTracker, pnl: PnLTracker) -> None:
        self.tracker = tracker
        self.pnl = pnl

        # Build strategy list in priority order (S1 > S2 > S3)
        self._all_strategies: list[BaseStrategy] = []
        if config.strategies.early_entry:
            self._all_strategies.append(EarlyEntryStrategy(tracker))
        if config.strategies.mid_game:
            self._all_strategies.append(MidGameStrategy(tracker))
        if config.strategies.late_scalp:
            self._all_strategies.append(LateScalpStrategy(tracker))

    def set_db_events(self, events: DbEventCollector) -> None:
        """Set the DB event collector on the engine and all strategies."""
        for strat in self._all_strategies:
            strat.set_db_events(events)

    @property
    def strategies(self) -> list[BaseStrategy]:
        return self._all_strategies

    def tick(self, signal: TASignal) -> None:
        """Main per-tick logic: tick active strategies or evaluate entries."""
        active = self._get_active()

        if active:
            # Tick the active strategy
            active.tick(signal)
            # If it just completed, harvest P&L
            if active.phase == StrategyPhase.COMPLETED and active.pnl_cents != 0:
                self.pnl.add(active.pnl_cents)
        else:
            # No active strategy — evaluate entry in priority order
            for strat in self._all_strategies:
                if strat.phase == StrategyPhase.PENDING and strat.should_enter(signal):
                    strat.enter(signal)
                    break  # Mutual exclusion: first match wins

    def on_market_expired(self, signal: TASignal) -> None:
        """Handle market expiry for all non-PENDING, non-COMPLETED strategies."""
        for strat in self._all_strategies:
            if strat.is_active:
                strat.on_market_expired(signal)
                if strat.pnl_cents != 0:
                    self.pnl.add(strat.pnl_cents)

    def reset(self) -> None:
        """Reset all strategies for a new market."""
        for strat in self._all_strategies:
            strat.reset()
        self.tracker.reset()

    def snapshots(self) -> list[StrategySnapshot]:
        return [s.snapshot() for s in self._all_strategies]

    def _get_active(self) -> BaseStrategy | None:
        for strat in self._all_strategies:
            if strat.is_active:
                return strat
        return None
