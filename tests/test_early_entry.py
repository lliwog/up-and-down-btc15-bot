import pytest

from bot.models.strategy_state import StrategyPhase
from bot.order_tracker.dryrun_tracker import DryRunOrderTracker
from bot.strategies.early_entry import EarlyEntryStrategy
from tests.conftest import make_signal


@pytest.fixture
def strat():
    tracker = DryRunOrderTracker()
    return EarlyEntryStrategy(tracker), tracker


class TestShouldEnter:
    def test_all_conditions_met(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=12, adjustedUp=0.68, marketUp=0.38, signal="BUY UP")
        assert s.should_enter(sig)

    def test_time_too_low(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=9, adjustedUp=0.68, marketUp=0.38, signal="BUY UP")
        assert not s.should_enter(sig)

    def test_ta_too_low(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=12, adjustedUp=0.60, marketUp=0.38, signal="BUY UP")
        assert not s.should_enter(sig)

    def test_price_too_high(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=12, adjustedUp=0.68, marketUp=0.42, signal="BUY UP")
        assert not s.should_enter(sig)

    def test_down_side(self, strat):
        s, _ = strat
        sig = make_signal(
            timeLeftMin=12, adjustedDown=0.68, marketDown=0.35,
            signal="BUY DOWN", adjustedUp=0.32, marketUp=0.65,
        )
        assert s.should_enter(sig)

    def test_no_trade_signal(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=12, adjustedUp=0.68, marketUp=0.38, signal="NO TRADE")
        assert not s.should_enter(sig)


class TestEntryAndFill:
    def test_buy_up_price_calculation(self, strat):
        s, tracker = strat
        sig = make_signal(timeLeftMin=12, adjustedUp=0.68, marketUp=0.38, signal="BUY UP")
        s.enter(sig)
        assert s.phase == StrategyPhase.ENTERING
        buy = tracker.get_order(s.buy_order_id)
        # 38 * 1.01 = 38.38 → round to 38
        assert buy.limit_price == 38

        sell = tracker.get_order(s.sell_order_id)
        # 38 * 1.40 = 53.2 → round to 53
        assert sell.limit_price == 53

    def test_buy_down_price_calculation(self, strat):
        s, tracker = strat
        sig = make_signal(
            timeLeftMin=12, adjustedDown=0.68, marketDown=0.38,
            signal="BUY DOWN", adjustedUp=0.32, marketUp=0.62,
        )
        s.enter(sig)
        buy = tracker.get_order(s.buy_order_id)
        # 38 * 0.99 = 37.62 → round to 38
        assert buy.limit_price == 38

    def test_full_lifecycle_buy_fills_then_sell_fills(self, strat):
        s, tracker = strat
        sig = make_signal(timeLeftMin=12, adjustedUp=0.68, marketUp=0.38, signal="BUY UP")
        s.enter(sig)

        # BUY fills (price at limit)
        tracker.update_prices(market_up=38, market_down=62)
        s.tick(sig)
        assert s.phase == StrategyPhase.EXITING

        # SELL fills
        tracker.update_prices(market_up=53, market_down=47)
        s.tick(sig)
        assert s.phase == StrategyPhase.COMPLETED
        assert s.outcome == "WIN"
        # P&L = (53 - 38) * 10 = 150 cents
        assert s.pnl_cents == 150


class TestExpiry:
    def test_buy_never_filled_no_trade(self, strat):
        s, tracker = strat
        sig = make_signal(timeLeftMin=12, adjustedUp=0.68, marketUp=0.38, signal="BUY UP")
        s.enter(sig)
        # Market expires without fill
        s.on_market_expired(sig)
        assert s.phase == StrategyPhase.COMPLETED
        assert s.outcome == "NO_TRADE"
        assert s.pnl_cents == 0

    def test_buy_filled_sell_not_filled_loss(self, strat):
        s, tracker = strat
        sig = make_signal(timeLeftMin=12, adjustedUp=0.68, marketUp=0.38, signal="BUY UP")
        s.enter(sig)
        tracker.update_prices(market_up=38, market_down=62)
        s.tick(sig)
        assert s.phase == StrategyPhase.EXITING

        # Expire without SELL filling
        s.on_market_expired(sig)
        assert s.phase == StrategyPhase.COMPLETED
        assert s.outcome == "LOSS"
        # Loss = -38 * 10 = -380 cents
        assert s.pnl_cents == -380
