from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from bot.models.strategy_state import StrategySnapshot


class BotState(BaseModel):
    # Mode
    mode: Literal["DRYRUN", "LIVE"]

    # Market data (from TA signal)
    market_slug: str = ""
    time_left_min: float = 0.0
    up_score: int = 0
    down_score: int = 0
    recommendation: str = ""
    current_price: float = 0.0
    price_to_beat: float = 0.0
    market_up: int = 0
    market_down: int = 0
    signal: str = ""
    adjusted_up: float = 0.0
    adjusted_down: float = 0.0

    # Strategies
    strategies: list[StrategySnapshot] = []

    # Global P&L
    global_pnl_cents: int = 0

    # Error state
    error: str | None = None
