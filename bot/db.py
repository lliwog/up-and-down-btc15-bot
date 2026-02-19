"""SQLite historical data store for TA signals, orders, and strategy runs."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from bot.models.order import Order, OrderStatus
from bot.models.ta_signal import TASignal

logger = logging.getLogger(__name__)

# ── Schema ──────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ta_signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    market_slug     TEXT    NOT NULL,
    time_left_min   REAL    NOT NULL,
    current_price   REAL    NOT NULL,
    price_to_beat   REAL    NOT NULL,
    spot_price      REAL    NOT NULL,
    up_score        INTEGER NOT NULL,
    down_score      INTEGER NOT NULL,
    raw_up          REAL    NOT NULL,
    adjusted_up     REAL    NOT NULL,
    adjusted_down   REAL    NOT NULL,
    time_decay      REAL    NOT NULL,
    regime          TEXT    NOT NULL,
    signal          TEXT    NOT NULL,
    recommendation  TEXT    NOT NULL,
    edge_up         REAL    NOT NULL,
    edge_down       REAL    NOT NULL,
    market_up       REAL    NOT NULL,
    market_down     REAL    NOT NULL,
    rsi             REAL    NOT NULL,
    vwap_slope      REAL    NOT NULL,
    macd_hist       REAL    NOT NULL,
    ingested_at     TEXT    NOT NULL,
    UNIQUE(timestamp, market_slug)
);

CREATE INDEX IF NOT EXISTS idx_ta_signals_timestamp
    ON ta_signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_ta_signals_market_slug_timestamp
    ON ta_signals(market_slug, timestamp);

CREATE TABLE IF NOT EXISTS markets (
    slug            TEXT PRIMARY KEY,
    first_seen_at   TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    order_type      TEXT NOT NULL,
    side            TEXT NOT NULL,
    size            INTEGER NOT NULL,
    limit_price     INTEGER NOT NULL,
    fill_price      INTEGER,
    status          TEXT NOT NULL,
    paired_buy_id   TEXT,
    strategy_name   TEXT NOT NULL,
    market_slug     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    filled_at       TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_market_slug
    ON orders(market_slug);
CREATE INDEX IF NOT EXISTS idx_orders_strategy_name
    ON orders(strategy_name);

CREATE TABLE IF NOT EXISTS strategy_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name   TEXT NOT NULL,
    market_slug     TEXT NOT NULL,
    phase           TEXT NOT NULL,
    outcome         TEXT,
    pnl_cents       INTEGER NOT NULL DEFAULT 0,
    entered_at      TEXT NOT NULL,
    completed_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_strategy_runs_market_slug
    ON strategy_runs(market_slug);
CREATE INDEX IF NOT EXISTS idx_strategy_runs_strategy_name
    ON strategy_runs(strategy_name);
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Database lifecycle ──────────────────────────────────────────────────────


async def open_db(db_path: str | Path) -> aiosqlite.Connection:
    """Open (or create) the SQLite database and ensure schema exists."""
    db = await aiosqlite.connect(str(db_path))
    await db.execute("PRAGMA journal_mode=WAL")
    await db.executescript(_SCHEMA)
    await db.commit()
    logger.info("Historical DB open: %s", db_path)
    return db


async def close_db(db: aiosqlite.Connection) -> None:
    """Close the database connection."""
    await db.close()
    logger.info("Historical DB closed")


# ── TA Signals ──────────────────────────────────────────────────────────────


async def insert_ta_signal(db: aiosqlite.Connection, signal: TASignal) -> bool:
    """Insert a TA signal row. Returns True if inserted, False if duplicate.

    Deduplication is by (timestamp, market_slug) UNIQUE constraint.
    """
    try:
        await db.execute(
            """INSERT OR IGNORE INTO ta_signals (
                timestamp, market_slug, time_left_min, current_price,
                price_to_beat, spot_price, up_score, down_score,
                raw_up, adjusted_up, adjusted_down, time_decay,
                regime, signal, recommendation,
                edge_up, edge_down, market_up, market_down,
                rsi, vwap_slope, macd_hist, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                signal.timestamp,
                signal.marketSlug,
                signal.timeLeftMin,
                signal.currentPrice,
                signal.priceToBeat,
                signal.spotPrice,
                signal.upScore,
                signal.downScore,
                signal.rawUp,
                signal.adjustedUp,
                signal.adjustedDown,
                signal.timeDecay,
                signal.regime,
                signal.signal,
                signal.recommendation,
                signal.edgeUp,
                signal.edgeDown,
                signal.marketUp,
                signal.marketDown,
                signal.rsi,
                signal.vwapSlope,
                signal.macdHist,
                _now_iso(),
            ),
        )
        return db.total_changes > 0
    except Exception:
        logger.exception("Failed to insert TA signal")
        return False


# ── Markets ─────────────────────────────────────────────────────────────────


async def upsert_market(db: aiosqlite.Connection, slug: str) -> None:
    """Insert or update the market slug with current timestamp."""
    now = _now_iso()
    await db.execute(
        """INSERT INTO markets (slug, first_seen_at, last_seen_at)
           VALUES (?, ?, ?)
           ON CONFLICT(slug) DO UPDATE SET last_seen_at = excluded.last_seen_at""",
        (slug, now, now),
    )


# ── Orders ──────────────────────────────────────────────────────────────────


async def insert_order(
    db: aiosqlite.Connection,
    order: Order,
    strategy_name: str,
    market_slug: str,
) -> None:
    """Insert a new order record."""
    await db.execute(
        """INSERT OR IGNORE INTO orders (
            order_id, order_type, side, size, limit_price,
            fill_price, status, paired_buy_id,
            strategy_name, market_slug, created_at, filled_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            order.order_id,
            order.order_type.value,
            order.side.value,
            order.size,
            order.limit_price,
            order.fill_price,
            order.status.value,
            order.paired_buy_id,
            strategy_name,
            market_slug,
            _now_iso(),
            None,
        ),
    )


async def update_order_fill(
    db: aiosqlite.Connection,
    order_id: str,
    fill_price: int,
) -> None:
    """Mark an order as FILLED with the given fill price."""
    await db.execute(
        """UPDATE orders
           SET status = ?, fill_price = ?, filled_at = ?
           WHERE order_id = ?""",
        (OrderStatus.FILLED.value, fill_price, _now_iso(), order_id),
    )


async def update_order_cancelled(
    db: aiosqlite.Connection,
    order_id: str,
) -> None:
    """Mark an order as CANCELLED."""
    await db.execute(
        """UPDATE orders SET status = ? WHERE order_id = ?""",
        (OrderStatus.CANCELLED.value, order_id),
    )


# ── Strategy Runs ───────────────────────────────────────────────────────────


async def insert_strategy_run(
    db: aiosqlite.Connection,
    strategy_name: str,
    market_slug: str,
    phase: str,
) -> int:
    """Insert a new strategy run. Returns the row id."""
    cursor = await db.execute(
        """INSERT INTO strategy_runs (
            strategy_name, market_slug, phase, outcome, pnl_cents, entered_at
        ) VALUES (?, ?, ?, ?, ?, ?)""",
        (strategy_name, market_slug, phase, None, 0, _now_iso()),
    )
    return cursor.lastrowid


async def update_strategy_run(
    db: aiosqlite.Connection,
    run_id: int,
    phase: str,
    outcome: str | None,
    pnl_cents: int,
) -> None:
    """Update a strategy run with final phase, outcome, and P&L."""
    await db.execute(
        """UPDATE strategy_runs
           SET phase = ?, outcome = ?, pnl_cents = ?, completed_at = ?
           WHERE id = ?""",
        (phase, outcome, pnl_cents, _now_iso(), run_id),
    )
