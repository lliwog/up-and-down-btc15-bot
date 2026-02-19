from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, computed_field, field_validator


class TASignal(BaseModel):
    timestamp: str
    marketSlug: str
    timeLeftMin: float
    currentPrice: float = 0.0
    priceToBeat: float = 0.0

    @field_validator("currentPrice", "priceToBeat", mode="before")
    @classmethod
    def _none_to_zero(cls, v: float | None) -> float:
        return 0.0 if v is None else v
    spotPrice: float
    upScore: int
    downScore: int
    rawUp: float
    adjustedUp: float
    adjustedDown: float
    timeDecay: float
    regime: str
    signal: str  # "BUY UP", "BUY DOWN", or "NO TRADE"
    recommendation: str
    edgeUp: float
    edgeDown: float
    marketUp: float  # dollars (e.g. 0.49)
    marketDown: float  # dollars (e.g. 0.51)
    rsi: float
    vwapSlope: float
    macdHist: float

    @computed_field  # type: ignore[prop-decorator]
    @property
    def side(self) -> Literal["UP", "DOWN"] | None:
        if self.signal == "BUY UP":
            return "UP"
        if self.signal == "BUY DOWN":
            return "DOWN"
        return None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ta_score(self) -> float:
        """The TA probability for the favored side (0-1)."""
        if self.side is None:
            return 0.0
        return self.adjustedUp if self.side == "UP" else self.adjustedDown

    @computed_field  # type: ignore[prop-decorator]
    @property
    def token_price(self) -> int:
        """Current token price in cents for the favored side."""
        if self.side is None:
            return 0
        return self.market_up_cents if self.side == "UP" else self.market_down_cents

    @computed_field  # type: ignore[prop-decorator]
    @property
    def market_up_cents(self) -> int:
        """Market UP price converted to cents."""
        return round(self.marketUp * 100)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def market_down_cents(self) -> int:
        """Market DOWN price converted to cents."""
        return round(self.marketDown * 100)
