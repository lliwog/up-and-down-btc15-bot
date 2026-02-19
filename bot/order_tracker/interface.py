from __future__ import annotations

from abc import ABC, abstractmethod

from bot.models.order import Order, OrderSide


class OrderTracker(ABC):
    @abstractmethod
    def submit_buy(self, side: OrderSide, size: int, price: int) -> str:
        """Submit a BUY order. Returns order_id."""

    @abstractmethod
    def submit_sell(
        self, side: OrderSide, size: int, price: int, paired_buy_id: str
    ) -> str:
        """Submit a SELL order linked to its BUY. Returns order_id."""

    @abstractmethod
    def is_filled(self, order_id: str) -> bool:
        """Check if an order has been filled."""

    @abstractmethod
    def get_fill_price(self, order_id: str) -> int | None:
        """Return fill price in cents, or None if not filled."""

    @abstractmethod
    def cancel(self, order_id: str) -> None:
        """Cancel an open order."""

    @abstractmethod
    def get_order(self, order_id: str) -> Order:
        """Return the full order record."""

    @abstractmethod
    def update_prices(self, market_up: int, market_down: int) -> None:
        """Called once per tick with current market prices.
        DryRun uses this to evaluate fills. Live is a no-op."""

    @abstractmethod
    def reset(self) -> None:
        """Cancel all open orders and clear state for a new market."""
