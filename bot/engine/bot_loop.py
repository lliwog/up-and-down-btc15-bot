from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from bot.config import BotConfig
from bot.db import close_db, insert_ta_signal, open_db
from bot.db_events import DbEventCollector
from bot.engine.market_manager import MarketManager
from bot.engine.pnl_tracker import PnLTracker
from bot.engine.strategy_engine import StrategyEngine
from bot.engine.ta_reader import read_ta_signal
from bot.models.bot_state import BotState
from bot.models.ta_signal import TASignal
from bot.order_tracker.dryrun_tracker import DryRunOrderTracker

logger = logging.getLogger(__name__)


class BotLoop:
    """Async 1-second tick loop that wires TA reader, market manager, order
    tracker, and strategy engine together."""

    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.tracker = DryRunOrderTracker()
        self.market_mgr = MarketManager()
        self.pnl = PnLTracker()
        self.engine = StrategyEngine(config, self.tracker, self.pnl)
        self._state = BotState(mode=config.mode)
        self._running = False
        self._db = None
        self._db_events = DbEventCollector()

        # Wire DB event collector into all components
        self.tracker.set_db_events(self._db_events)
        self.market_mgr.set_db_events(self._db_events)
        self.engine.set_db_events(self._db_events)

    @property
    def state(self) -> BotState:
        return self._state

    async def run_forever(self) -> None:
        self._running = True
        self._db = await open_db(self.config.db_path)
        try:
            while self._running:
                await self._tick()
                await asyncio.sleep(1)
        finally:
            if self._db:
                await close_db(self._db)
                self._db = None

    def stop(self) -> None:
        self._running = False

    async def _tick(self) -> None:
        try:
            signal = await read_ta_signal(self.config.ta_json_path)
            self._process_signal(signal)
            self._build_state(signal)
            # Flush DB events collected during the sync phase
            await self._flush_db(signal)
        except FileNotFoundError:
            self._state.error = f"TA file not found: {self.config.ta_json_path}"
        except Exception as e:
            logger.exception("Tick error")
            self._state.error = str(e)

    async def _flush_db(self, signal: TASignal) -> None:
        """Persist TA signal and any buffered DB events in a single commit."""
        if self._db is None:
            return
        try:
            await insert_ta_signal(self._db, signal)
            await self._db_events.flush(self._db)
            await self._db.commit()
        except Exception:
            logger.exception("DB flush error")
            self._db_events.clear()

    def _process_signal(self, signal: TASignal) -> None:
        # Check for market change
        changed = self.market_mgr.check_market_change(signal.marketSlug)
        if changed:
            # Expire active strategies from the previous market
            self.engine.on_market_expired(signal)
            self.engine.reset()

        # Update simulated fills
        self.tracker.update_prices(signal.market_up_cents, signal.market_down_cents)

        # Tick strategies
        self.engine.tick(signal)

    def _build_state(self, signal: TASignal) -> None:
        self._state = BotState(
            mode=self.config.mode,
            market_slug=signal.marketSlug,
            time_left_min=signal.timeLeftMin,
            up_score=signal.upScore,
            down_score=signal.downScore,
            recommendation=signal.recommendation,
            current_price=signal.currentPrice,
            price_to_beat=signal.priceToBeat,
            market_up=signal.market_up_cents,
            market_down=signal.market_down_cents,
            signal=signal.signal,
            adjusted_up=signal.adjustedUp,
            adjusted_down=signal.adjustedDown,
            strategies=self.engine.snapshots(),
            global_pnl_cents=self.pnl.total_cents,
            error=None,
        )

    # For testing: run a single tick synchronously with a given signal
    def tick_with_signal(self, signal: TASignal) -> None:
        self._process_signal(signal)
        self._build_state(signal)
