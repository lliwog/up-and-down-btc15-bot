from __future__ import annotations

from enum import Enum

from pydantic import BaseModel

from bot.models.order import Order


class StrategyName(str, Enum):
    EARLY_ENTRY = "early_entry"
    MID_GAME = "mid_game"
    LATE_SCALP = "late_scalp"


class StrategyPhase(str, Enum):
    PENDING = "PENDING"
    ENTERING = "ENTERING"
    RUNNING = "RUNNING"
    EXITING = "EXITING"
    COMPLETED = "COMPLETED"


class StrategySnapshot(BaseModel):
    name: StrategyName
    phase: StrategyPhase
    pnl_cents: int = 0  # P&L in cents for this strategy in current market
    orders: list[Order] = []
    outcome: str | None = None  # "WIN", "LOSS", "NO_TRADE", or None
