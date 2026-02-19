from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class OrderSide(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class OrderType(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


class Order(BaseModel):
    order_id: str
    order_type: OrderType
    side: OrderSide
    size: int
    limit_price: int  # cents
    fill_price: int | None = None
    status: OrderStatus = OrderStatus.OPEN
    paired_buy_id: str | None = None  # SELL orders link to their BUY
