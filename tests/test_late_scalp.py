import pytest

from bot.models.order import OrderSide
from bot.models.strategy_state import StrategyPhase
from bot.order_tracker.dryrun_tracker import DryRunOrderTracker
from bot.strategies.late_scalp import LateScalpStrategy
from tests.conftest import make_signal


@pytest.fixture
def strat():
    tracker = DryRunOrderTracker()
    return LateScalpStrategy(tracker), tracker


class TestShouldEnter:
    def test_all_conditions_met(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=1.5, marketUp=0.95, signal="BUY UP")
        assert s.should_enter(sig)

    def test_time_too_high(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=2.5, marketUp=0.95, signal="BUY UP")
        assert not s.should_enter(sig)

    def test_price_too_low(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=1.5, marketUp=0.93, signal="BUY UP")
        assert not s.should_enter(sig)

    def test_no_ta_threshold(self, strat):
        """S3 has no TA score requirement."""
        s, _ = strat
        sig = make_signal(timeLeftMin=1.5, marketUp=0.95, adjustedUp=0.30, signal="BUY UP")
        assert s.should_enter(sig)

    def test_no_trade_signal(self, strat):
        s, _ = strat
        sig = make_signal(timeLeftMin=1.5, marketUp=0.95, signal="NO TRADE")
        assert not s.should_enter(sig)


class TestTwoPhaseLifecycle:
    def test_buy_at_93_cents(self, strat):
        s, tracker = strat
        sig = make_signal(timeLeftMin=1.5, marketUp=0.95, signal="BUY UP")
        s.enter(sig)
        buy = tracker.get_order(s.buy_order_id)
        assert buy.limit_price == 94
        assert buy.size == 100
        assert s.phase == StrategyPhase.ENTERING

    def test_buy_fills_transitions_to_running(self, strat):
        s, tracker = strat
        sig = make_signal(timeLeftMin=1.5, marketUp=0.95, signal="BUY UP")
        s.enter(sig)
        tracker.update_prices(market_up=94, market_down=6)
        s.tick(sig)
        assert s.phase == StrategyPhase.RUNNING

    def test_price_dip_triggers_sell(self, strat):
        s, tracker = strat
        sig = make_signal(timeLeftMin=1.5, marketUp=0.95, signal="BUY UP")
        s.enter(sig)
        # BUY fills
        tracker.update_prices(market_up=94, market_down=6)
        s.tick(sig)
        assert s.phase == StrategyPhase.RUNNING

        # Price dips to 50
        sig2 = make_signal(timeLeftMin=1.0, marketUp=0.50, signal="BUY UP")
        s.tick(sig2)
        assert s.phase == StrategyPhase.EXITING
        sell = tracker.get_order(s.sell_order_id)
        assert sell.limit_price == 50

        # SELL fills immediately (price is at 50)
        tracker.update_prices(market_up=50, market_down=50)
        s.tick(sig2)
        assert s.phase == StrategyPhase.COMPLETED
        assert s.outcome == "LOSS"
        # P&L: (50 - 94) * 100 = -4400 cents
        assert s.pnl_cents == -4400


class TestExpiry:
    def test_buy_never_filled_no_trade(self, strat):
        s, tracker = strat
        sig = make_signal(timeLeftMin=1.5, marketUp=0.95, signal="BUY UP")
        s.enter(sig)
        s.on_market_expired(sig)
        assert s.outcome == "NO_TRADE"
        assert s.pnl_cents == 0

    def test_buy_filled_market_resolves_in_favor_win(self, strat):
        """BUY UP at 94¢, market resolves UP → shares worth 100¢ → WIN."""
        s, tracker = strat
        sig = make_signal(timeLeftMin=1.5, marketUp=0.95, signal="BUY UP")
        s.enter(sig)
        tracker.update_prices(market_up=94, market_down=6)
        s.tick(sig)
        assert s.phase == StrategyPhase.RUNNING

        # Market expires, still favoring UP
        expire_sig = make_signal(timeLeftMin=0, marketUp=0.96, signal="BUY UP")
        s.on_market_expired(expire_sig)
        assert s.outcome == "WIN"
        # (100 - 94) * 100 = 600 cents
        assert s.pnl_cents == 600

    def test_buy_filled_market_resolves_against_loss(self, strat):
        """BUY UP at 94¢, market resolves DOWN → shares worth 0¢ → LOSS."""
        s, tracker = strat
        sig = make_signal(timeLeftMin=1.5, marketUp=0.95, signal="BUY UP")
        s.enter(sig)
        tracker.update_prices(market_up=94, market_down=6)
        s.tick(sig)

        expire_sig = make_signal(timeLeftMin=0, signal="BUY DOWN")
        s.on_market_expired(expire_sig)
        assert s.outcome == "LOSS"
        # -94 * 100 = -9400 cents
        assert s.pnl_cents == -9400

    def test_buy_filled_sell_submitted_not_filled_win(self, strat):
        """BUY fills, SELL submitted but not filled, market resolves in favor → WIN."""
        s, tracker = strat
        sig = make_signal(timeLeftMin=1.5, marketUp=0.95, signal="BUY UP")
        s.enter(sig)
        tracker.update_prices(market_up=94, market_down=6)
        s.tick(sig)

        # Price dips to 50, SELL submitted
        sig2 = make_signal(timeLeftMin=0.5, marketUp=0.50, signal="BUY UP")
        s.tick(sig2)
        assert s.phase == StrategyPhase.EXITING

        # But SELL doesn't fill (price bounces up) and market expires in favor
        expire_sig = make_signal(timeLeftMin=0, marketUp=0.96, signal="BUY UP")
        s.on_market_expired(expire_sig)
        assert s.outcome == "WIN"
        assert s.pnl_cents == 600
