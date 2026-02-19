import pytest

from bot.config import BotConfig, StrategyFlags
from bot.engine.pnl_tracker import PnLTracker
from bot.engine.strategy_engine import StrategyEngine
from bot.models.strategy_state import StrategyName, StrategyPhase
from bot.order_tracker.dryrun_tracker import DryRunOrderTracker
from tests.conftest import make_signal


@pytest.fixture
def components():
    config = BotConfig(strategies=StrategyFlags())
    tracker = DryRunOrderTracker()
    pnl = PnLTracker()
    engine = StrategyEngine(config, tracker, pnl)
    return engine, tracker, pnl


class TestMutualExclusion:
    def test_only_highest_priority_enters(self, components):
        engine, tracker, pnl = components
        # S1 conditions: >10min, TA>65%, price<40
        sig = make_signal(
            timeLeftMin=12, adjustedUp=0.68, marketUp=0.38, signal="BUY UP",
        )
        engine.tick(sig)
        phases = {s.name: s.phase for s in engine.strategies}
        assert phases[StrategyName.EARLY_ENTRY] == StrategyPhase.ENTERING
        assert phases[StrategyName.MID_GAME] == StrategyPhase.PENDING
        assert phases[StrategyName.LATE_SCALP] == StrategyPhase.PENDING

    def test_s2_enters_when_s1_conditions_not_met(self, components):
        engine, tracker, pnl = components
        # S2 conditions: 5-10min, TA>70%, price<45
        sig = make_signal(
            timeLeftMin=7, adjustedUp=0.72, marketUp=0.42, signal="BUY UP",
        )
        engine.tick(sig)
        phases = {s.name: s.phase for s in engine.strategies}
        assert phases[StrategyName.EARLY_ENTRY] == StrategyPhase.PENDING
        assert phases[StrategyName.MID_GAME] == StrategyPhase.ENTERING
        assert phases[StrategyName.LATE_SCALP] == StrategyPhase.PENDING

    def test_s3_enters_when_s1_s2_not_met(self, components):
        engine, tracker, pnl = components
        sig = make_signal(
            timeLeftMin=1.5, marketUp=0.95, signal="BUY UP",
        )
        engine.tick(sig)
        phases = {s.name: s.phase for s in engine.strategies}
        assert phases[StrategyName.EARLY_ENTRY] == StrategyPhase.PENDING
        assert phases[StrategyName.MID_GAME] == StrategyPhase.PENDING
        assert phases[StrategyName.LATE_SCALP] == StrategyPhase.ENTERING

    def test_no_entry_when_one_already_active(self, components):
        engine, tracker, pnl = components
        # Enter S1
        sig1 = make_signal(
            timeLeftMin=12, adjustedUp=0.68, marketUp=0.38, signal="BUY UP",
        )
        engine.tick(sig1)

        # Now conditions change to favor S2 as well, but S1 is still active
        sig2 = make_signal(
            timeLeftMin=7, adjustedUp=0.72, marketUp=0.42, signal="BUY UP",
        )
        engine.tick(sig2)
        phases = {s.name: s.phase for s in engine.strategies}
        assert phases[StrategyName.EARLY_ENTRY] == StrategyPhase.ENTERING
        assert phases[StrategyName.MID_GAME] == StrategyPhase.PENDING

    def test_no_entry_on_no_trade(self, components):
        engine, tracker, pnl = components
        sig = make_signal(
            timeLeftMin=12, adjustedUp=0.68, marketUp=0.38, signal="NO TRADE",
        )
        engine.tick(sig)
        for s in engine.strategies:
            assert s.phase == StrategyPhase.PENDING


class TestPnLAccumulation:
    def test_pnl_accumulated_on_completion(self, components):
        engine, tracker, pnl = components
        sig = make_signal(
            timeLeftMin=12, adjustedUp=0.68, marketUp=0.38, signal="BUY UP",
        )
        engine.tick(sig)
        # BUY fills (limit=38)
        tracker.update_prices(market_up=38, market_down=62)
        engine.tick(sig)
        # SELL fills (limit=53)
        tracker.update_prices(market_up=53, market_down=47)
        engine.tick(sig)

        s1 = engine.strategies[0]
        assert s1.phase == StrategyPhase.COMPLETED
        assert pnl.total_cents == 150  # (53-38)*10

    def test_pnl_from_expiry(self, components):
        engine, tracker, pnl = components
        sig = make_signal(
            timeLeftMin=12, adjustedUp=0.68, marketUp=0.38, signal="BUY UP",
        )
        engine.tick(sig)
        # BUY fills (limit=38)
        tracker.update_prices(market_up=38, market_down=62)
        engine.tick(sig)

        # Expire with SELL unfilled
        expire_sig = make_signal(timeLeftMin=0, signal="BUY UP")
        engine.on_market_expired(expire_sig)
        assert pnl.total_cents == -380  # -38*10


class TestReset:
    def test_reset_returns_all_to_pending(self, components):
        engine, tracker, pnl = components
        sig = make_signal(
            timeLeftMin=12, adjustedUp=0.68, marketUp=0.38, signal="BUY UP",
        )
        engine.tick(sig)
        engine.reset()
        for s in engine.strategies:
            assert s.phase == StrategyPhase.PENDING


class TestDisabledStrategies:
    def test_disabled_strategy_not_present(self):
        config = BotConfig(strategies=StrategyFlags(mid_game=False))
        tracker = DryRunOrderTracker()
        pnl = PnLTracker()
        engine = StrategyEngine(config, tracker, pnl)
        names = [s.name for s in engine.strategies]
        assert StrategyName.MID_GAME not in names
        assert StrategyName.EARLY_ENTRY in names
        assert StrategyName.LATE_SCALP in names


class TestIdleWhenNoConditionsMet:
    def test_no_entry_when_conditions_not_met(self, components):
        engine, tracker, pnl = components
        sig = make_signal(
            timeLeftMin=3, adjustedUp=0.50, marketUp=0.60, signal="BUY UP",
        )
        engine.tick(sig)
        for s in engine.strategies:
            assert s.phase == StrategyPhase.PENDING
