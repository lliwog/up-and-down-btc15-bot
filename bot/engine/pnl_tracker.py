from __future__ import annotations


class PnLTracker:
    """Accumulates P&L in cents across markets."""

    def __init__(self) -> None:
        self._total_cents: int = 0

    @property
    def total_cents(self) -> int:
        return self._total_cents

    def add(self, cents: int) -> None:
        self._total_cents += cents

    def reset(self) -> None:
        self._total_cents = 0
