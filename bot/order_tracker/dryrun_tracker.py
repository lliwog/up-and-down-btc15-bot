from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from bot.models.order import Order, OrderSide, OrderStatus, OrderType
from bot.order_tracker.interface import OrderTracker

if TYPE_CHECKING:
    from bot.db_events import DbEventCollector


class DryRunOrderTracker(OrderTracker):
    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._db_events: DbEventCollector | None = None
        self._strategy_name: str = ""
        self._market_slug: str = ""

    def set_db_events(self, events: DbEventCollector) -> None:
        self._db_events = events

    def set_context(self, strategy_name: str, market_slug: str) -> None:
        """Set the current strategy/market context for order DB writes."""
        self._strategy_name = strategy_name
        self._market_slug = market_slug

    def submit_buy(self, side: OrderSide, size: int, price: int) -> str:
        oid = str(uuid.uuid4())
        order = Order(
            order_id=oid,
            order_type=OrderType.BUY,
            side=side,
            size=size,
            limit_price=price,
        )
        self._orders[oid] = order
        if self._db_events:
            self._db_events.order_inserted(order, self._strategy_name, self._market_slug)
        return oid

    def submit_sell(
        self, side: OrderSide, size: int, price: int, paired_buy_id: str
    ) -> str:
        oid = str(uuid.uuid4())
        order = Order(
            order_id=oid,
            order_type=OrderType.SELL,
            side=side,
            size=size,
            limit_price=price,
            paired_buy_id=paired_buy_id,
        )
        self._orders[oid] = order
        if self._db_events:
            self._db_events.order_inserted(order, self._strategy_name, self._market_slug)
        return oid

    def is_filled(self, order_id: str) -> bool:
        return self._orders[order_id].status == OrderStatus.FILLED

    def get_fill_price(self, order_id: str) -> int | None:
        return self._orders[order_id].fill_price

    def cancel(self, order_id: str) -> None:
        order = self._orders[order_id]
        if order.status == OrderStatus.OPEN:
            order.status = OrderStatus.CANCELLED
            if self._db_events:
                self._db_events.order_cancelled(order_id)

    def get_order(self, order_id: str) -> Order:
        return self._orders[order_id]

    def update_prices(self, market_up: int, market_down: int) -> None:
        """Simulate fills: process BUYs first, then SELLs."""
        prices = {OrderSide.UP: market_up, OrderSide.DOWN: market_down}

        # Pass 1: BUYs
        for order in self._orders.values():
            if order.status != OrderStatus.OPEN:
                continue
            if order.order_type != OrderType.BUY:
                continue
            current = prices[order.side]
            if current <= order.limit_price:
                order.status = OrderStatus.FILLED
                order.fill_price = order.limit_price
                if self._db_events:
                    self._db_events.order_filled(order.order_id, order.limit_price)

        # Pass 2: SELLs (only if paired BUY is filled)
        for order in self._orders.values():
            if order.status != OrderStatus.OPEN:
                continue
            if order.order_type != OrderType.SELL:
                continue
            # Guard: paired BUY must be filled first
            if order.paired_buy_id and not self.is_filled(order.paired_buy_id):
                continue
            current = prices[order.side]
            if current >= order.limit_price:
                order.status = OrderStatus.FILLED
                order.fill_price = order.limit_price
                if self._db_events:
                    self._db_events.order_filled(order.order_id, order.limit_price)

    def reset(self) -> None:
        for order in self._orders.values():
            if order.status == OrderStatus.OPEN:
                order.status = OrderStatus.CANCELLED
                if self._db_events:
                    self._db_events.order_cancelled(order.order_id)
        self._orders.clear()
