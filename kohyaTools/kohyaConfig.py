#!/usr/bin/env python3
"""
kohyaConfig.py

Shared config loader/saver for kohya routines.
Default config path: ~/.config/kohya/kohyaConfig.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

defaultConfigPath = Path.home() / ".config" / "kohya" / "kohyaConfig.json"


def loadConfig() -> Dict[str, Any]:
    defaultConfigPath.parent.mkdir(parents=True, exist_ok=True)

    if not defaultConfigPath.exists():
        data: Dict[str, Any] = {}
        defaultConfigPath.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return data

    text = defaultConfigPath.read_text(encoding="utf-8").strip()
    if not text:
        return {}

    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"config file is not a json object: {defaultConfigPath}")
    return data


def saveConfig(data: Dict[str, Any]) -> None:
    defaultConfigPath.parent.mkdir(parents=True, exist_ok=True)
    defaultConfigPath.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def getCfgValue(cfg: Dict[str, Any], key: str, defaultValue: Any) -> Any:
    value = cfg.get(key, defaultValue)
    return value


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
