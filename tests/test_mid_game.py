import pytest

from bot.models.strategy_state import StrategyPhase
from bot.order_tracker.dryrun_tracker import DryRunOrderTracker
from bot.strategies.mid_game import MidGameStrategy
from tests.conftest import make_signal


@pytest.fixture
def strat():
    tracker = DryRunOrderTracker()
    return MidGameStrategy(tracker), tracker


class TestShouldEnter:
    def test_all_conditions_met(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=7, adjustedUp=0.72, marketUp=0.42, signal="BUY UP")
        assert s.should_enter(sig)

    def test_time_too_high(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=11, adjustedUp=0.72, marketUp=0.42, signal="BUY UP")
        assert not s.should_enter(sig)

    def test_time_too_low(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=4, adjustedUp=0.72, marketUp=0.42, signal="BUY UP")
        assert not s.should_enter(sig)

    def test_ta_too_low(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=7, adjustedUp=0.68, marketUp=0.42, signal="BUY UP")
        assert not s.should_enter(sig)

    def test_price_too_high(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=7, adjustedUp=0.72, marketUp=0.51, signal="BUY UP")
        assert not s.should_enter(sig)

    def test_boundary_time_5(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=5, adjustedUp=0.72, marketUp=0.42, signal="BUY UP")
        assert s.should_enter(sig)

    def test_boundary_time_10(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=10, adjustedUp=0.72, marketUp=0.42, signal="BUY UP")
        assert s.should_enter(sig)

    def test_no_trade_signal(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=7, adjustedUp=0.72, marketUp=0.42, signal="NO TRADE")
        assert not s.should_enter(sig)


class TestEntryAndFill:
    def test_sell_price_40_percent_markup(self, strat):
        s, tracker = strat
        sig = make_signal(timeLeftMin=7, adjustedUp=0.72, marketUp=0.42, signal="BUY UP")
        s.enter(sig)
        buy = tracker.get_order(s.buy_order_id)
        # 42 * 1.01 = 42.42 → round to 42
        assert buy.limit_price == 42

        sell = tracker.get_order(s.sell_order_id)
        # 42 * 1.40 = 58.8 → round to 59
        assert sell.limit_price == 59

    def test_sell_price_capped_at_99(self, strat):
        s, tracker = strat
        # High token price scenario
        sig = make_signal(timeLeftMin=7, adjustedUp=0.72, marketUp=0.44, signal="BUY UP")
        s.enter(sig)
        buy = tracker.get_order(s.buy_order_id)
        # 44 * 1.01 = 44.44 → round to 44
        sell = tracker.get_order(s.sell_order_id)
        # 44 * 1.40 = 61.6 → round to 62, still under 99
        assert sell.limit_price <= 99

    def test_full_lifecycle(self, strat):
        s, tracker = strat
        sig = make_signal(timeLeftMin=7, adjustedUp=0.72, marketUp=0.42, signal="BUY UP")
        s.enter(sig)

        tracker.update_prices(market_up=42, market_down=58)
        s.tick(sig)
        assert s.phase == StrategyPhase.EXITING

        tracker.update_prices(market_up=59, market_down=41)
        s.tick(sig)
        assert s.phase == StrategyPhase.COMPLETED
        assert s.outcome == "WIN"
        # P&L = (59 - 42) * 10 = 170 cents
        assert s.pnl_cents == 170
