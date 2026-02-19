import pytest

from bot.config import BotConfig
from bot.engine.bot_loop import BotLoop
from bot.models.strategy_state import StrategyName, StrategyPhase
from tests.conftest import make_signal


@pytest.fixture
def bot():
    config = BotConfig()
    return BotLoop(config)


class TestBotLoopIntegration:
    def test_s1_full_lifecycle(self, bot: BotLoop):
        """S1 enters, BUY fills, SELL fills → WIN with P&L."""
        # Tick 1: S1 conditions met, enters
        sig1 = make_signal(
            timeLeftMin=12, adjustedUp=0.68, marketUp=0.38, signal="BUY UP",
        )
        bot.tick_with_signal(sig1)
        state = bot.state
        s1 = next(s for s in state.strategies if s.name == StrategyName.EARLY_ENTRY)
        assert s1.phase == StrategyPhase.ENTERING

        # Tick 2: BUY fills (price at 38 = buy limit)
        sig2 = make_signal(
            timeLeftMin=11.5, adjustedUp=0.68, marketUp=0.38, signal="BUY UP",
        )
        bot.tick_with_signal(sig2)
        s1 = next(s for s in bot.state.strategies if s.name == StrategyName.EARLY_ENTRY)
        assert s1.phase == StrategyPhase.EXITING

        # Tick 3: SELL fills (price rises to 53 = sell limit)
        sig3 = make_signal(
            timeLeftMin=11, adjustedUp=0.68, marketUp=0.53, signal="BUY UP",
        )
        bot.tick_with_signal(sig3)
        s1 = next(s for s in bot.state.strategies if s.name == StrategyName.EARLY_ENTRY)
        assert s1.phase == StrategyPhase.COMPLETED
        assert s1.outcome == "WIN"
        assert s1.pnl_cents == 150  # (53-38)*10
        assert bot.state.global_pnl_cents == 150

    def test_market_change_resets_strategies(self, bot: BotLoop):
        """Market slug change triggers reset to PENDING."""
        sig1 = make_signal(
            timeLeftMin=12, adjustedUp=0.68, marketUp=0.38,
            signal="BUY UP", marketSlug="market-1",
        )
        bot.tick_with_signal(sig1)
        s1 = next(s for s in bot.state.strategies if s.name == StrategyName.EARLY_ENTRY)
        assert s1.phase == StrategyPhase.ENTERING

        # New market slug → reset
        sig2 = make_signal(
            timeLeftMin=14, adjustedUp=0.50, marketUp=0.50,
            signal="BUY UP", marketSlug="market-2",
        )
        bot.tick_with_signal(sig2)
        for s in bot.state.strategies:
            assert s.phase == StrategyPhase.PENDING

    def test_s3_two_phase_win(self, bot: BotLoop):
        """S3: BUY at 93, price never dips to 50, market resolves in favor → WIN."""
        # Tick 1: S3 conditions met
        sig1 = make_signal(
            timeLeftMin=1.5, marketUp=0.95, signal="BUY UP",
        )
        bot.tick_with_signal(sig1)
        s3 = next(s for s in bot.state.strategies if s.name == StrategyName.LATE_SCALP)
        assert s3.phase == StrategyPhase.ENTERING

        # Tick 2: BUY fills
        sig2 = make_signal(timeLeftMin=1.2, marketUp=0.94, signal="BUY UP")
        bot.tick_with_signal(sig2)
        s3 = next(s for s in bot.state.strategies if s.name == StrategyName.LATE_SCALP)
        assert s3.phase == StrategyPhase.RUNNING

        # Tick 3: Price stays high, market changes (resolves in favor)
        sig3 = make_signal(
            timeLeftMin=14, marketUp=0.50, signal="BUY UP",
            marketSlug="new-market",
        )
        bot.tick_with_signal(sig3)
        # P&L from S3 WIN: (100-94)*100 = 600
        assert bot.state.global_pnl_cents == 600

    def test_no_ta_file_sets_error(self, bot: BotLoop):
        """When TA file is missing, state.error is set."""
        import asyncio
        asyncio.get_event_loop().run_until_complete(bot._tick())
        assert bot.state.error is not None
        assert "not found" in bot.state.error

    def test_pnl_accumulates_across_markets(self, bot: BotLoop):
        """P&L persists across market resets."""
        # Market 1: S1 full WIN (BUY at 38, SELL at 53)
        sig1 = make_signal(
            timeLeftMin=12, adjustedUp=0.68, marketUp=0.38,
            signal="BUY UP", marketSlug="m1",
        )
        bot.tick_with_signal(sig1)
        bot.tick_with_signal(make_signal(
            timeLeftMin=11, marketUp=0.38, signal="BUY UP", marketSlug="m1",
        ))
        bot.tick_with_signal(make_signal(
            timeLeftMin=10, marketUp=0.53, signal="BUY UP", marketSlug="m1",
        ))
        assert bot.state.global_pnl_cents == 150

        # Market 2: S2 full WIN (BUY at 42, SELL at 59)
        bot.tick_with_signal(make_signal(
            timeLeftMin=7, adjustedUp=0.72, marketUp=0.42,
            signal="BUY UP", marketSlug="m2",
        ))
        # BUY fills (42 limit, price=42)
        bot.tick_with_signal(make_signal(
            timeLeftMin=6, marketUp=0.42, signal="BUY UP", marketSlug="m2",
        ))
        # SELL fills (59 limit, price=59)
        bot.tick_with_signal(make_signal(
            timeLeftMin=5, marketUp=0.59, signal="BUY UP", marketSlug="m2",
        ))
        # 150 + 170 = 320
        assert bot.state.global_pnl_cents == 320
