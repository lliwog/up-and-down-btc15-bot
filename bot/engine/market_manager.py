from __future__ import annotations


class MarketManager:
    """Detects marketSlug changes across ticks."""

    def __init__(self) -> None:
        self._current_slug: str | None = None

    @property
    def current_slug(self) -> str | None:
        return self._current_slug

    def check_market_change(self, slug: str) -> bool:
        """Return True if the market has changed (or is the first tick)."""
        if self._current_slug is None:
            self._current_slug = slug
            return False  # First tick is not a "change"
        if slug != self._current_slug:
            self._current_slug = slug
            return True
        return False

    def reset(self) -> None:
        self._current_slug = None
