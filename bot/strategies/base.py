from __future__ import annotations

from abc import ABC, abstractmethod

from bot.models.order import Order, OrderStatus
from bot.models.strategy_state import StrategyName, StrategyPhase, StrategySnapshot
from bot.models.ta_signal import TASignal
from bot.order_tracker.interface import OrderTracker


class BaseStrategy(ABC):
    name: StrategyName

    def __init__(self, tracker: OrderTracker) -> None:
        self.tracker = tracker
        self.phase = StrategyPhase.PENDING
        self.buy_order_id: str | None = None
        self.sell_order_id: str | None = None
        self.pnl_cents: int = 0
        self.outcome: str | None = None

    # ── Public interface ──

    @abstractmethod
    def should_enter(self, signal: TASignal) -> bool:
        """Check if entry conditions are met (called by StrategyEngine)."""

    def enter(self, signal: TASignal) -> None:
        """Submit BUY (and possibly SELL) orders, transition to ENTERING."""
        self._do_enter(signal)
        self.phase = StrategyPhase.ENTERING

    def tick(self, signal: TASignal) -> None:
        """Called every second while strategy is active (not PENDING/COMPLETED)."""
        if self.phase == StrategyPhase.ENTERING:
            self._tick_entering(signal)
        elif self.phase == StrategyPhase.RUNNING:
            self._tick_running(signal)
        elif self.phase == StrategyPhase.EXITING:
            self._tick_exiting(signal)

    def on_market_expired(self, signal: TASignal) -> None:
        """Handle market expiry. Subclasses override for custom logic."""
        self._do_expire(signal)

    def reset(self) -> None:
        """Reset to PENDING for a new market."""
        self.phase = StrategyPhase.PENDING
        self.buy_order_id = None
        self.sell_order_id = None
        self.pnl_cents = 0
        self.outcome = None

    def snapshot(self) -> StrategySnapshot:
        orders: list[Order] = []
        if self.buy_order_id:
            orders.append(self.tracker.get_order(self.buy_order_id))
        if self.sell_order_id:
            orders.append(self.tracker.get_order(self.sell_order_id))
        return StrategySnapshot(
            name=self.name,
            phase=self.phase,
            pnl_cents=self.pnl_cents,
            orders=orders,
            outcome=self.outcome,
        )

    @property
    def is_active(self) -> bool:
        return self.phase in (
            StrategyPhase.ENTERING,
            StrategyPhase.RUNNING,
            StrategyPhase.EXITING,
        )

    # ── Hooks for subclasses ──

    @abstractmethod
    def _do_enter(self, signal: TASignal) -> None:
        """Submit orders. Called by enter()."""

    def _tick_entering(self, signal: TASignal) -> None:
        """Default ENTERING tick: check if BUY filled."""
        if self.buy_order_id and self.tracker.is_filled(self.buy_order_id):
            self._on_buy_filled(signal)

    def _on_buy_filled(self, signal: TASignal) -> None:
        """Called when BUY fills. Default: transition to EXITING (S1/S2 pattern)."""
        self.phase = StrategyPhase.EXITING

    def _tick_running(self, signal: TASignal) -> None:
        """Override in strategies that use RUNNING phase (S3)."""

    def _tick_exiting(self, signal: TASignal) -> None:
        """Default EXITING tick: check if SELL filled."""
        if self.sell_order_id and self.tracker.is_filled(self.sell_order_id):
            self._on_sell_filled()

    def _on_sell_filled(self) -> None:
        """Called when SELL fills. Compute P&L and complete."""
        buy_price = self.tracker.get_fill_price(self.buy_order_id)
        sell_price = self.tracker.get_fill_price(self.sell_order_id)
        buy_order = self.tracker.get_order(self.buy_order_id)
        self.pnl_cents = (sell_price - buy_price) * buy_order.size
        self.outcome = "WIN" if self.pnl_cents > 0 else "LOSS"
        self.phase = StrategyPhase.COMPLETED

    @abstractmethod
    def _do_expire(self, signal: TASignal) -> None:
        """Handle market expiry. Cancel orders, set outcome."""
