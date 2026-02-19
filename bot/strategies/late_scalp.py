# Strategy behavior (S3: Late Scalp):
# - Activates very late (<2 minutes left) when price is elevated (>94¢), ignoring
#   TA score by design.
# - Submits a BUY at 94¢ and waits for fill. After BUY fill, it enters RUNNING and
#   watches for a sharp dip.
# - On dip to ≤50¢, submits paired SELL at 50¢. If no SELL fill by expiry, outcome
#   is resolved against market result (WIN if bought side resolves true, else LOSS).
from __future__ import annotations

from bot.models.order import OrderSide
from bot.models.strategy_state import StrategyName, StrategyPhase
from bot.models.ta_signal import TASignal
from bot.strategies.base import BaseStrategy


class LateScalpStrategy(BaseStrategy):
    name = StrategyName.LATE_SCALP

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._buy_side: OrderSide | None = None

    def should_enter(self, signal: TASignal) -> bool:
        if signal.side is None:
            return False
        # No TA threshold — only time and price
        return signal.timeLeftMin < 2 and signal.token_price > 94

    def _do_enter(self, signal: TASignal) -> None:
        self._buy_side = OrderSide(signal.side)
        # BUY at 94¢
        self.buy_order_id = self.tracker.submit_buy(
            self._buy_side, size=100, price=94
        )

    def _on_buy_filled(self, signal: TASignal) -> None:
        """BUY filled → go to RUNNING (wait for price dip to 50¢)."""
        self.phase = StrategyPhase.RUNNING

    def _tick_running(self, signal: TASignal) -> None:
        """Monitor for price dip to ≤50¢, then submit SELL at 50¢."""
        token_price = (
            signal.market_up_cents if self._buy_side == OrderSide.UP else signal.market_down_cents
        )
        if token_price <= 50:
            # Set tracker context for the SELL order DB write
            if hasattr(self.tracker, 'set_context'):
                self.tracker.set_context(self.name.value, signal.marketSlug)
            self.sell_order_id = self.tracker.submit_sell(
                self._buy_side, size=100, price=50, paired_buy_id=self.buy_order_id
            )
            self.phase = StrategyPhase.EXITING

    def _do_expire(self, signal: TASignal) -> None:
        buy_filled = self.buy_order_id and self.tracker.is_filled(self.buy_order_id)

        if self.buy_order_id:
            self.tracker.cancel(self.buy_order_id)
        if self.sell_order_id:
            self.tracker.cancel(self.sell_order_id)

        if not buy_filled:
            # BUY never filled → no trade
            self.outcome = "NO_TRADE"
            self.pnl_cents = 0
        elif self.sell_order_id and self.tracker.is_filled(self.sell_order_id):
            # SELL already filled — P&L was computed in _on_sell_filled
            pass
        else:
            # BUY filled, SELL not filled (or not submitted) → check market resolution
            buy_price = self.tracker.get_fill_price(self.buy_order_id)
            buy_order = self.tracker.get_order(self.buy_order_id)
            # Market resolves: does the signal's side match our buy side?
            # If signal side == buy side at expiry, our tokens resolve at 100¢
            if signal.side is not None and OrderSide(signal.side) == self._buy_side:
                # WIN: shares resolve at 100¢ each
                self.pnl_cents = (100 - buy_price) * buy_order.size
                self.outcome = "WIN"
            else:
                # LOSS: shares resolve at 0¢
                self.pnl_cents = -buy_price * buy_order.size
                self.outcome = "LOSS"

        self.phase = StrategyPhase.COMPLETED
        self._emit_run_completed()

    def reset(self) -> None:
        super().reset()
        self._buy_side = None
