# Strategy behavior (S1: Early Entry):
# - Activates early in the market (>10 minutes left) when TA confidence is strong
#   and token price is still relatively low.
# - Places one BUY near current price (+1% for UP, -1% for DOWN), then immediately
#   places a paired SELL at +40% from BUY price (capped at 99¢).
# - If BUY never fills by expiry: NO_TRADE. If BUY fills but SELL does not: LOSS at
#   BUY cost basis.
from __future__ import annotations

from bot.models.order import OrderSide
from bot.models.strategy_state import StrategyName
from bot.models.ta_signal import TASignal
from bot.strategies.base import BaseStrategy


class EarlyEntryStrategy(BaseStrategy):
    name = StrategyName.EARLY_ENTRY

    def should_enter(self, signal: TASignal) -> bool:
        if signal.side is None:
            return False
        return (
            signal.timeLeftMin > 10
            and signal.ta_score > 0.65
            and signal.token_price < 40
        )

    def _do_enter(self, signal: TASignal) -> None:
        side = OrderSide(signal.side)
        token_price = signal.token_price

        # BUY: +1% for UP, -1% for DOWN
        if side == OrderSide.UP:
            buy_price = round(token_price * 1.01)
        else:
            buy_price = round(token_price * 0.99)

        self.buy_order_id = self.tracker.submit_buy(side, size=10, price=buy_price)

        # SELL: BUY limit price + 40%, capped at 99¢
        sell_price = min(round(buy_price * 1.40), 99)
        self.sell_order_id = self.tracker.submit_sell(
            side, size=10, price=sell_price, paired_buy_id=self.buy_order_id
        )

    def _do_expire(self, signal: TASignal) -> None:
        buy_filled = self.buy_order_id and self.tracker.is_filled(self.buy_order_id)

        # Cancel any open orders
        if self.buy_order_id:
            self.tracker.cancel(self.buy_order_id)
        if self.sell_order_id:
            self.tracker.cancel(self.sell_order_id)

        if not buy_filled:
            # BUY never filled → no trade
            self.outcome = "NO_TRADE"
            self.pnl_cents = 0
        else:
            # BUY filled but SELL didn't fill → loss
            buy_price = self.tracker.get_fill_price(self.buy_order_id)
            buy_order = self.tracker.get_order(self.buy_order_id)
            self.pnl_cents = -buy_price * buy_order.size
            self.outcome = "LOSS"

        self.phase = self.phase.COMPLETED
        self._emit_run_completed()
