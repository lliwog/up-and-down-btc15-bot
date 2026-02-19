from pathlib import Path

import pytest
import yaml

from bot.config import BotConfig, load_config


def test_default_config():
    cfg = BotConfig()
    assert cfg.mode == "DRYRUN"
    assert cfg.strategies.early_entry is True
    assert cfg.port == 8080


def test_load_from_yaml(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        yaml.dump(
            {
                "ta_json_dir": "/tmp/ta",
                "mode": "DRYRUN",
                "strategies": {"early_entry": False},
                "port": 9090,
            }
        )
    )
    cfg = load_config(cfg_file)
    assert cfg.ta_json_dir == "/tmp/ta"
    assert cfg.strategies.early_entry is False
    assert cfg.port == 9090


def test_ta_json_path():
    cfg = BotConfig(ta_json_dir="/data", ta_json_filename="out.json")
    assert cfg.ta_json_path == Path("/data/out.json")


def test_reject_private_key_in_yaml(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        yaml.dump(
            {
                "mode": "LIVE",
                "polymarket_private_key": "do-not-store-secrets-here",
            }
        )
    )

    with pytest.raises(ValueError, match="BOT_POLYMARKET_PRIVATE_KEY"):
        load_config(cfg_file)
