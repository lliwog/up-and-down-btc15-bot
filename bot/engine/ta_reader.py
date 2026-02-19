from __future__ import annotations

import json
from pathlib import Path

import aiofiles

from bot.models.ta_signal import TASignal


async def read_ta_signal(path: Path) -> TASignal:
    """Read and parse the TA JSON file asynchronously."""
    async with aiofiles.open(path, "r") as f:
        data = json.loads(await f.read())
    return TASignal(**data)
