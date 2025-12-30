#!/usr/bin/env python3
"""
kohyaConfig.py

Shared configuration loader/saver for kohya routines.
Default config path: ~/.config/kohya/kohyaConfig.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "kohya" / "kohyaConfig.json"


def loadConfig() -> Dict[str, Any]:
    """Load configuration from the default config file, creating it if needed."""
    DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not DEFAULT_CONFIG_PATH.exists():
        data: Dict[str, Any] = {}
        DEFAULT_CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return data

    text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8").strip()
    if not text:
        return {}

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"config file is not a json object: {DEFAULT_CONFIG_PATH}")
    return data


def saveConfig(data: Dict[str, Any]) -> None:
    """Save configuration to the default config file."""
    DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_CONFIG_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def getCfgValue(cfg: Dict[str, Any], key: str, defaultValue: Any) -> Any:
    """Get a config value with a default fallback."""
    return cfg.get(key, defaultValue)


def updateCfgFromArgs(cfg: Dict[str, Any], updates: Dict[str, Any]) -> bool:
    """
    Updates cfg in-place for keys in updates where value is not None and differs.
    Returns True if cfg changed.
    """
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if cfg.get(key) != value:
            cfg[key] = value
            changed = True
    return changed
