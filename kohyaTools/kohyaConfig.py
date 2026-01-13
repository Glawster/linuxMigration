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
    """
    Load configuration from the default config file, creating it if needed.
    
    Returns:
        Dictionary containing configuration data
        
    Raises:
        ValueError: If config file exists but is not valid JSON or not a dict
        IOError: If config file cannot be read or written
    """
    try:
        DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as e:
        raise IOError(f"Cannot create config directory: {e}") from e

    if not DEFAULT_CONFIG_PATH.exists():
        data: Dict[str, Any] = {}
        try:
            DEFAULT_CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        except (OSError, PermissionError) as e:
            raise IOError(f"Cannot write config file: {e}") from e
        return data

    try:
        text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8").strip()
    except (OSError, PermissionError) as e:
        raise IOError(f"Cannot read config file: {e}") from e
    
    if not text:
        return {}

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in config file: {e}") from e
    
    if not isinstance(data, dict):
        raise ValueError(f"config file is not a json object: {DEFAULT_CONFIG_PATH}")
    return data


def saveConfig(data: Dict[str, Any]) -> None:
    """
    Save configuration to the default config file.
    
    Args:
        data: Configuration dictionary to save
        
    Raises:
        TypeError: If data is not a dictionary
        IOError: If config file cannot be written
    """
    if not isinstance(data, dict):
        raise TypeError(f"config data must be a dict, got {type(data).__name__}")
    
    try:
        DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_CONFIG_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, PermissionError) as e:
        raise IOError(f"Cannot write config file: {e}") from e


def getCfgValue(cfg: Dict[str, Any], key: str, defaultValue: Any) -> Any:
    """
    Get a config value with a default fallback.
    
    Args:
        cfg: Configuration dictionary
        key: Configuration key to retrieve
        defaultValue: Default value if key is not found
        
    Returns:
        Configuration value or default
    """
    return cfg.get(key, defaultValue)


def updateConfigFromArgs(cfg: Dict[str, Any], updates: Dict[str, Any]) -> bool:
    """
    Update cfg in-place for keys in updates where value is not None and differs.
    
    Args:
        cfg: Configuration dictionary to update (modified in-place)
        updates: Dictionary of updates to apply
        
    Returns:
        True if cfg was changed, False otherwise
    """
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if cfg.get(key) != value:
            logger.info(f"{prefix} config update: {key}: {cfg.get(key)!r} -> {value!r}")
            cfg[key] = value
            changed = True
    return changed
