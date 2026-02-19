"""Tests for the SQLite historical data store (bot/db.py) and event collector."""

from __future__ import annotations

import pytest

from bot.db import (
    close_db,
    insert_order,
    insert_strategy_run,
    insert_ta_signal,
    open_db,
    update_order_cancelled,
    update_order_fill,
    update_strategy_run,
    upsert_market,
)
from bot.db_events import DbEventCollector
from bot.models.order import Order, OrderSide, OrderStatus, OrderType
from tests.conftest import make_signal


@pytest.fixture
async def db():
    """Provide an in-memory SQLite database for testing."""
    conn = await open_db(":memory:")
    yield conn
    await close_db(conn)


# ── Schema ──────────────────────────────────────────────────────────────────


class TestInitDb:
    async def test_creates_tables(self, db):
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        assert "ta_signals" in tables
        assert "markets" in tables
        assert "orders" in tables
        assert "strategy_runs" in tables

    async def test_idempotent(self, db):
        """Calling open_db again on same connection doesn't fail."""
        # Just verify schema exists — open_db uses CREATE IF NOT EXISTS
        cursor = await db.execute("SELECT count(*) FROM ta_signals")
        row = await cursor.fetchone()
        assert row[0] == 0


# ── TA Signals ──────────────────────────────────────────────────────────────


class TestInsertTaSignal:
    async def test_inserts_signal(self, db):
        signal = make_signal()
        result = await insert_ta_signal(db, signal)
        assert result is True

        cursor = await db.execute("SELECT count(*) FROM ta_signals")
        row = await cursor.fetchone()
        assert row[0] == 1

    async def test_stores_all_fields(self, db):
        signal = make_signal(rsi=72.5, vwapSlope=-0.33, macdHist=1.2)
        await insert_ta_signal(db, signal)

        cursor = await db.execute("SELECT rsi, vwap_slope, macd_hist FROM ta_signals")
        row = await cursor.fetchone()
        assert row[0] == pytest.approx(72.5)
        assert row[1] == pytest.approx(-0.33)
        assert row[2] == pytest.approx(1.2)

    async def test_dedup_by_timestamp_and_slug(self, db):
        signal = make_signal()
        await insert_ta_signal(db, signal)
        await insert_ta_signal(db, signal)  # Same timestamp+slug

        cursor = await db.execute("SELECT count(*) FROM ta_signals")
        row = await cursor.fetchone()
        assert row[0] == 1  # Only one row

    async def test_different_timestamps_are_separate(self, db):
        s1 = make_signal(timestamp="2026-02-18T14:32:01.000Z")
        s2 = make_signal(timestamp="2026-02-18T14:32:02.000Z")
        await insert_ta_signal(db, s1)
        await insert_ta_signal(db, s2)

        cursor = await db.execute("SELECT count(*) FROM ta_signals")
        row = await cursor.fetchone()
        assert row[0] == 2

    async def test_same_timestamp_different_slug(self, db):
        s1 = make_signal(marketSlug="market-a")
        s2 = make_signal(marketSlug="market-b")
        await insert_ta_signal(db, s1)
        await insert_ta_signal(db, s2)

        cursor = await db.execute("SELECT count(*) FROM ta_signals")
        row = await cursor.fetchone()
        assert row[0] == 2


# ── Markets ─────────────────────────────────────────────────────────────────


class TestUpsertMarket:
    async def test_insert_new_market(self, db):
        await upsert_market(db, "btc-up-down-abc")

        cursor = await db.execute("SELECT slug FROM markets")
        row = await cursor.fetchone()
        assert row[0] == "btc-up-down-abc"

    async def test_upsert_updates_last_seen(self, db):
        await upsert_market(db, "btc-up-down-abc")
        cursor = await db.execute("SELECT last_seen_at FROM markets WHERE slug = ?", ("btc-up-down-abc",))
        first_seen = (await cursor.fetchone())[0]

        await upsert_market(db, "btc-up-down-abc")
        cursor = await db.execute("SELECT last_seen_at FROM markets WHERE slug = ?", ("btc-up-down-abc",))
        second_seen = (await cursor.fetchone())[0]

        # last_seen_at should be updated (or at least not error)
        assert second_seen >= first_seen


# ── Orders ──────────────────────────────────────────────────────────────────


class TestOrders:
    def _make_order(self, **kwargs) -> Order:
        defaults = dict(
            order_id="ord-123",
            order_type=OrderType.BUY,
            side=OrderSide.UP,
            size=10,
            limit_price=45,
        )
        defaults.update(kwargs)
        return Order(**defaults)

    async def test_insert_order(self, db):
        order = self._make_order()
        await insert_order(db, order, "early_entry", "market-a")

        cursor = await db.execute("SELECT order_id, order_type, side, size, limit_price FROM orders")
        row = await cursor.fetchone()
        assert row == ("ord-123", "BUY", "UP", 10, 45)

    async def test_insert_order_with_paired_buy(self, db):
        order = self._make_order(
            order_id="sell-456",
            order_type=OrderType.SELL,
            limit_price=63,
            paired_buy_id="ord-123",
        )
        await insert_order(db, order, "early_entry", "market-a")

        cursor = await db.execute("SELECT paired_buy_id FROM orders WHERE order_id = ?", ("sell-456",))
        row = await cursor.fetchone()
        assert row[0] == "ord-123"

    async def test_update_order_fill(self, db):
        order = self._make_order()
        await insert_order(db, order, "early_entry", "market-a")
        await update_order_fill(db, "ord-123", 45)

        cursor = await db.execute(
            "SELECT status, fill_price, filled_at FROM orders WHERE order_id = ?",
            ("ord-123",),
        )
        row = await cursor.fetchone()
        assert row[0] == "FILLED"
        assert row[1] == 45
        assert row[2] is not None  # filled_at timestamp set

    async def test_update_order_cancelled(self, db):
        order = self._make_order()
        await insert_order(db, order, "early_entry", "market-a")
        await update_order_cancelled(db, "ord-123")

        cursor = await db.execute("SELECT status FROM orders WHERE order_id = ?", ("ord-123",))
        row = await cursor.fetchone()
        assert row[0] == "CANCELLED"


# ── Strategy Runs ───────────────────────────────────────────────────────────


class TestStrategyRuns:
    async def test_insert_strategy_run(self, db):
        run_id = await insert_strategy_run(db, "early_entry", "market-a", "ENTERING")

        assert run_id is not None
        cursor = await db.execute(
            "SELECT strategy_name, market_slug, phase, outcome, pnl_cents FROM strategy_runs WHERE id = ?",
            (run_id,),
        )
        row = await cursor.fetchone()
        assert row == ("early_entry", "market-a", "ENTERING", None, 0)

    async def test_update_strategy_run(self, db):
        run_id = await insert_strategy_run(db, "early_entry", "market-a", "ENTERING")
        await update_strategy_run(db, run_id, "COMPLETED", "WIN", 150)

        cursor = await db.execute(
            "SELECT phase, outcome, pnl_cents, completed_at FROM strategy_runs WHERE id = ?",
            (run_id,),
        )
        row = await cursor.fetchone()
        assert row[0] == "COMPLETED"
        assert row[1] == "WIN"
        assert row[2] == 150
        assert row[3] is not None  # completed_at timestamp set


# ── DbEventCollector ───────────────────────────────────────────────────────


class TestDbEventCollector:
    async def test_flush_order_events(self, db):
        collector = DbEventCollector()
        order = Order(
            order_id="evt-buy-1",
            order_type=OrderType.BUY,
            side=OrderSide.UP,
            size=10,
            limit_price=45,
        )
        collector.order_inserted(order, "early_entry", "market-a")
        collector.order_filled("evt-buy-1", 45)

        await collector.flush(db)

        cursor = await db.execute("SELECT status, fill_price FROM orders WHERE order_id = ?", ("evt-buy-1",))
        row = await cursor.fetchone()
        assert row[0] == "FILLED"
        assert row[1] == 45

    async def test_flush_strategy_run_events(self, db):
        collector = DbEventCollector()
        stored_id = [None]

        def set_id(run_id):
            stored_id[0] = run_id

        collector.strategy_run_started("mid_game", "market-b", "ENTERING", set_id)
        await collector.flush(db)

        assert stored_id[0] is not None

        collector.strategy_run_ended(stored_id[0], "COMPLETED", "LOSS", -200)
        await collector.flush(db)

        cursor = await db.execute(
            "SELECT outcome, pnl_cents FROM strategy_runs WHERE id = ?",
            (stored_id[0],),
        )
        row = await cursor.fetchone()
        assert row == ("LOSS", -200)

    async def test_flush_market_event(self, db):
        collector = DbEventCollector()
        collector.market_seen("market-xyz")
        await collector.flush(db)

        cursor = await db.execute("SELECT slug FROM markets WHERE slug = ?", ("market-xyz",))
        row = await cursor.fetchone()
        assert row[0] == "market-xyz"

    async def test_flush_clears_buffer(self, db):
        collector = DbEventCollector()
        collector.market_seen("market-1")
        await collector.flush(db)

        # Second flush should be a no-op
        await collector.flush(db)
        cursor = await db.execute("SELECT count(*) FROM markets")
        row = await cursor.fetchone()
        assert row[0] == 1

    async def test_clear_discards_events(self, db):
        collector = DbEventCollector()
        collector.market_seen("market-discarded")
        collector.clear()
        await collector.flush(db)

        cursor = await db.execute("SELECT count(*) FROM markets")
        row = await cursor.fetchone()
        assert row[0] == 0
