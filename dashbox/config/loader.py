from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .env import runtime_config_values_from_env
from .model import CONFIG_FILE_TOP_LEVEL_KEYS, Config
from .parse import parse_subscriptions

def load_config(path: str | None) -> Config:
    if not path:
        return load_config_data({}, apply_env=True)
    raw_path = Path(path)
    if not raw_path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    data = json.loads(raw_path.read_text(encoding="utf-8-sig"))
    return load_config_data(data, apply_env=True)


def load_config_data(data: dict[str, Any], *, apply_env: bool = True) -> Config:
    if not isinstance(data, dict):
        raise ValueError("config root must be a JSON object")
    values: dict[str, Any] = {key: value for key, value in data.items() if key in CONFIG_FILE_TOP_LEVEL_KEYS}
    if apply_env:
        values.update(runtime_config_values_from_env())
    if "subs" in data:
        values["subs"] = parse_subscriptions(data["subs"])
    return Config(**values)


def parse_config_data(data: dict[str, Any], *, apply_env: bool = True) -> Config:
    return load_config_data(data, apply_env=apply_env)
