from __future__ import annotations

from bot.models.order import Order, OrderSide
from bot.order_tracker.interface import OrderTracker


class LiveOrderTracker(OrderTracker):
    """Stub for future Polymarket CLOB API integration."""

    def submit_buy(self, side: OrderSide, size: int, price: int) -> str:
        raise NotImplementedError("LIVE mode not yet implemented")

    def submit_sell(
        self, side: OrderSide, size: int, price: int, paired_buy_id: str
    ) -> str:
        raise NotImplementedError("LIVE mode not yet implemented")

    def is_filled(self, order_id: str) -> bool:
        raise NotImplementedError("LIVE mode not yet implemented")

    def get_fill_price(self, order_id: str) -> int | None:
        raise NotImplementedError("LIVE mode not yet implemented")

    def cancel(self, order_id: str) -> None:
        raise NotImplementedError("LIVE mode not yet implemented")

    def get_order(self, order_id: str) -> Order:
        raise NotImplementedError("LIVE mode not yet implemented")

    def update_prices(self, market_up: int, market_down: int) -> None:
        raise NotImplementedError("LIVE mode not yet implemented")

    def reset(self) -> None:
        raise NotImplementedError("LIVE mode not yet implemented")
