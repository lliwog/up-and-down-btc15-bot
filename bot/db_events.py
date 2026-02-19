"""Collects DB write events during synchronous tick processing.

Since strategy/tracker methods are synchronous but DB writes are async,
this module buffers events during the sync phase. The async BotLoop._tick()
flushes them after processing completes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import aiosqlite

from bot.models.order import Order


@dataclass
class OrderInsertEvent:
    order: Order
    strategy_name: str
    market_slug: str


@dataclass
class OrderFillEvent:
    order_id: str
    fill_price: int


@dataclass
class OrderCancelEvent:
    order_id: str


@dataclass
class StrategyRunStartEvent:
    strategy_name: str
    market_slug: str
    phase: str
    # Callback to store the run_id back on the strategy
    set_run_id: callable  # type: ignore[type-arg]


@dataclass
class StrategyRunEndEvent:
    run_id: int
    phase: str
    outcome: str | None
    pnl_cents: int


@dataclass
class MarketSeenEvent:
    slug: str


@dataclass
class DbEventCollector:
    """Accumulates DB write events for later async flushing."""

    _events: list = field(default_factory=list)

    def order_inserted(self, order: Order, strategy_name: str, market_slug: str) -> None:
        self._events.append(OrderInsertEvent(order, strategy_name, market_slug))

    def order_filled(self, order_id: str, fill_price: int) -> None:
        self._events.append(OrderFillEvent(order_id, fill_price))

    def order_cancelled(self, order_id: str) -> None:
        self._events.append(OrderCancelEvent(order_id))

    def strategy_run_started(
        self, strategy_name: str, market_slug: str, phase: str, set_run_id: callable  # type: ignore[type-arg]
    ) -> None:
        self._events.append(StrategyRunStartEvent(strategy_name, market_slug, phase, set_run_id))

    def strategy_run_ended(
        self, run_id: int, phase: str, outcome: str | None, pnl_cents: int
    ) -> None:
        self._events.append(StrategyRunEndEvent(run_id, phase, outcome, pnl_cents))

    def market_seen(self, slug: str) -> None:
        self._events.append(MarketSeenEvent(slug))

    async def flush(self, db: aiosqlite.Connection) -> None:
        """Write all buffered events to the database, then clear the buffer."""
        from bot.db import (
            insert_order,
            insert_strategy_run,
            update_order_cancelled,
            update_order_fill,
            update_strategy_run,
            upsert_market,
        )

        for event in self._events:
            if isinstance(event, OrderInsertEvent):
                await insert_order(db, event.order, event.strategy_name, event.market_slug)
            elif isinstance(event, OrderFillEvent):
                await update_order_fill(db, event.order_id, event.fill_price)
            elif isinstance(event, OrderCancelEvent):
                await update_order_cancelled(db, event.order_id)
            elif isinstance(event, StrategyRunStartEvent):
                run_id = await insert_strategy_run(
                    db, event.strategy_name, event.market_slug, event.phase
                )
                event.set_run_id(run_id)
            elif isinstance(event, StrategyRunEndEvent):
                await update_strategy_run(
                    db, event.run_id, event.phase, event.outcome, event.pnl_cents
                )
            elif isinstance(event, MarketSeenEvent):
                await upsert_market(db, event.slug)

        self._events.clear()

    def clear(self) -> None:
        self._events.clear()
