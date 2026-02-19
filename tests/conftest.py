from __future__ import annotations

import json
from pathlib import Path

import pytest

from bot.models.ta_signal import TASignal
from bot.order_tracker.dryrun_tracker import DryRunOrderTracker


@pytest.fixture
def tracker() -> DryRunOrderTracker:
    return DryRunOrderTracker()


def make_signal(**overrides) -> TASignal:
    """Create a TASignal with sensible defaults, overriding any field."""
    defaults = {
        "timestamp": "2026-02-18T14:32:01.123Z",
        "marketSlug": "will-btc-go-up-or-down-in-the-next-15-minutes-02-18-2026-2-30-pm",
        "timeLeftMin": 8.0,
        "currentPrice": 96432.17,
        "priceToBeat": 96410.50,
        "spotPrice": 96445,
        "upScore": 7,
        "downScore": 3,
        "rawUp": 0.7,
        "adjustedUp": 0.61,
        "adjustedDown": 0.39,
        "timeDecay": 0.55,
        "regime": "TREND_UP",
        "signal": "BUY UP",
        "recommendation": "UP:MID:strong",
        "edgeUp": 0.12,
        "edgeDown": -0.12,
        "marketUp": 0.49,
        "marketDown": 0.51,
        "rsi": 58.3,
        "vwapSlope": 1.24,
        "macdHist": 0.47,
    }
    defaults.update(overrides)
    return TASignal(**defaults)


def write_signal_file(tmp_path: Path, signal: TASignal, filename: str = "signal.json") -> Path:
    """Write a TASignal to a JSON file and return the file path."""
    fpath = tmp_path / filename
    fpath.write_text(json.dumps(signal.model_dump(), default=str))
    return fpath
