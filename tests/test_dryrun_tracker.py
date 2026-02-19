import pytest

from bot.models.order import OrderSide, OrderStatus, OrderType
from bot.order_tracker.dryrun_tracker import DryRunOrderTracker


@pytest.fixture
def tracker() -> DryRunOrderTracker:
    return DryRunOrderTracker()


class TestBuyFill:
    def test_buy_fills_when_price_at_limit(self, tracker: DryRunOrderTracker):
        oid = tracker.submit_buy(OrderSide.UP, 10, 40)
        tracker.update_prices(market_up=40, market_down=60)
        assert tracker.is_filled(oid)
        assert tracker.get_fill_price(oid) == 40

    def test_buy_fills_when_price_below_limit(self, tracker: DryRunOrderTracker):
        oid = tracker.submit_buy(OrderSide.UP, 10, 40)
        tracker.update_prices(market_up=38, market_down=62)
        assert tracker.is_filled(oid)

    def test_buy_does_not_fill_when_price_above_limit(self, tracker: DryRunOrderTracker):
        oid = tracker.submit_buy(OrderSide.UP, 10, 40)
        tracker.update_prices(market_up=42, market_down=58)
        assert not tracker.is_filled(oid)

    def test_buy_down_side(self, tracker: DryRunOrderTracker):
        oid = tracker.submit_buy(OrderSide.DOWN, 10, 55)
        tracker.update_prices(market_up=45, market_down=55)
        assert tracker.is_filled(oid)


class TestSellFill:
    def test_sell_fills_when_price_at_limit(self, tracker: DryRunOrderTracker):
        buy_id = tracker.submit_buy(OrderSide.UP, 10, 40)
        sell_id = tracker.submit_sell(OrderSide.UP, 10, 52, paired_buy_id=buy_id)
        # BUY fills, then SELL fills
        tracker.update_prices(market_up=40, market_down=60)
        assert tracker.is_filled(buy_id)
        # SELL needs price >= 52
        tracker.update_prices(market_up=52, market_down=48)
        assert tracker.is_filled(sell_id)
        assert tracker.get_fill_price(sell_id) == 52

    def test_sell_does_not_fill_before_buy(self, tracker: DryRunOrderTracker):
        """SELL must not fill until paired BUY is filled."""
        buy_id = tracker.submit_buy(OrderSide.UP, 10, 30)
        sell_id = tracker.submit_sell(OrderSide.UP, 10, 52, paired_buy_id=buy_id)
        # Price is high enough for SELL but BUY hasn't filled (price > buy limit)
        tracker.update_prices(market_up=55, market_down=45)
        assert not tracker.is_filled(buy_id)
        assert not tracker.is_filled(sell_id)

    def test_sell_fills_same_tick_as_buy(self, tracker: DryRunOrderTracker):
        """BUY and SELL can both fill in the same tick (BUYs processed first)."""
        buy_id = tracker.submit_buy(OrderSide.UP, 10, 50)
        sell_id = tracker.submit_sell(OrderSide.UP, 10, 50, paired_buy_id=buy_id)
        tracker.update_prices(market_up=50, market_down=50)
        assert tracker.is_filled(buy_id)
        assert tracker.is_filled(sell_id)


class TestCancel:
    def test_cancel_open_order(self, tracker: DryRunOrderTracker):
        oid = tracker.submit_buy(OrderSide.UP, 10, 40)
        tracker.cancel(oid)
        order = tracker.get_order(oid)
        assert order.status == OrderStatus.CANCELLED

    def test_cancel_filled_order_is_noop(self, tracker: DryRunOrderTracker):
        oid = tracker.submit_buy(OrderSide.UP, 10, 40)
        tracker.update_prices(market_up=38, market_down=62)
        tracker.cancel(oid)
        assert tracker.get_order(oid).status == OrderStatus.FILLED


class TestReset:
    def test_reset_cancels_and_clears(self, tracker: DryRunOrderTracker):
        oid = tracker.submit_buy(OrderSide.UP, 10, 40)
        tracker.reset()
        # After reset, internal state is cleared
        with pytest.raises(KeyError):
            tracker.get_order(oid)
