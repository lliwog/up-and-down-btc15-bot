from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.db_events import DbEventCollector


class MarketManager:
    """Detects marketSlug changes across ticks."""

    def __init__(self) -> None:
        self._current_slug: str | None = None
        self._db_events: DbEventCollector | None = None

    def set_db_events(self, events: DbEventCollector) -> None:
        self._db_events = events

    @property
    def current_slug(self) -> str | None:
        return self._current_slug

    def check_market_change(self, slug: str) -> bool:
        """Return True if the market has changed (or is the first tick)."""
        if self._current_slug is None:
            self._current_slug = slug
            if self._db_events:
                self._db_events.market_seen(slug)
            return False  # First tick is not a "change"
        if slug != self._current_slug:
            self._current_slug = slug
            if self._db_events:
                self._db_events.market_seen(slug)
            return True
        return False

    def reset(self) -> None:
        self._current_slug = None
