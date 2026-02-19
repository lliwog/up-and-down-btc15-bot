from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class StrategyFlags(BaseModel):
    early_entry: bool = True
    mid_game: bool = True
    late_scalp: bool = True


class BotConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BOT_")

    ta_json_dir: str = "."
    ta_json_filename: str = "signal.json"
    mode: Literal["DRYRUN", "LIVE"] = "DRYRUN"
    polymarket_private_key: str = ""
    strategies: StrategyFlags = StrategyFlags()
    host: str = "0.0.0.0"
    port: int = 8080
    db_path: str = "bot_history.db"

    @property
    def ta_json_path(self) -> Path:
        return Path(self.ta_json_dir) / self.ta_json_filename


def load_config(path: str | Path | None = None) -> BotConfig:
    """Load config from a YAML file, falling back to env vars / defaults."""
    if path is None:
        return BotConfig()
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if "polymarket_private_key" in data:
        raise ValueError(
            "Do not set 'polymarket_private_key' in config YAML. "
            "Use BOT_POLYMARKET_PRIVATE_KEY environment variable instead."
        )
    return BotConfig(**data)
