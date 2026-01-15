#!/usr/bin/env python3
"""
kohyaConfig.py

Shared configuration loader/saver for kohya routines.
Default config path: ~/.config/kohya/kohyaConfig.json

Conventions:
- logging via organiseMyProjects.logUtils (injected via setLogger)
- --dry-run: prefix is "...[]" for dry-run operations, "..." otherwise
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "kohya" / "kohyaConfig.json"

logger: Optional[logging.Logger] = None


def setLogger(externalLogger: logging.Logger) -> None:
    """
    Inject a logger from the calling script.
    
    kohyaConfig does not create its own logger; it uses the caller's.
    
    Args:
        externalLogger: Logger instance to use for logging
    """
    global logger
    logger = externalLogger


def _log(level: str, message: str, prefix: str = "...") -> None:
    """
    Internal logging function with prefix support.
    
    Args:
        level: Log level ("info", "warning", "error")
        message: Log message
        prefix: Logging prefix (typically "..." or "...[]" for dry-run)
    """
    fullMessage = f"{prefix} {message}" if prefix else message
    
    if logger is None:
        print(fullMessage)
        return
    
    if level == "error":
        logger.error(fullMessage)
    elif level == "warning":
        logger.warning(fullMessage)
    else:
        logger.info(fullMessage)


def loadConfig(prefix: str = "...") -> Dict[str, Any]:
    """
    Load configuration from the default config file, creating it if needed.
    
    Args:
        prefix: Logging prefix (typically "..." or "...[]" for dry-run)
    
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
            _log("info", f"created config file: {DEFAULT_CONFIG_PATH}", prefix)
        except (OSError, PermissionError) as e:
            raise IOError(f"Cannot write config file: {e}") from e
        return data

    try:
        text = DEFAULT_CONFIG_PATH.read_text(encoding="utf-8").strip()
        _log("info", f"loaded config: {DEFAULT_CONFIG_PATH}", prefix)
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


def saveConfig(data: Dict[str, Any], prefix: str = "...", dryRun: bool = False) -> None:
    """
    Save configuration to the default config file.
    
    Args:
        data: Configuration dictionary to save
        prefix: Logging prefix (typically "..." or "...[]" for dry-run)
        dryRun: If True, simulate saving without writing
        
    Raises:
        TypeError: If data is not a dictionary
        IOError: If config file cannot be written
    """
    if not isinstance(data, dict):
        raise TypeError(f"config data must be a dict, got {type(data).__name__}")
    
    if dryRun:
        _log("info", f"saved config: {DEFAULT_CONFIG_PATH}", prefix)
        return
    
    try:
        DEFAULT_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEFAULT_CONFIG_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _log("info", f"saved config: {DEFAULT_CONFIG_PATH}", prefix)
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


def updateConfigFromArgs(cfg: Dict[str, Any], updates: Dict[str, Any], prefix: str = "...") -> bool:
    """
    Update cfg in-place for keys in updates where value is not None and differs.
    
    Args:
        cfg: Configuration dictionary to update (modified in-place)
        updates: Dictionary of updates to apply
        prefix: Logging prefix (typically "..." or "...[]" for dry-run)
        
    Returns:
        True if cfg was changed, False otherwise
    """
    changed = False
    changedKeys = []
    for key, value in updates.items():
        if value is None:
            continue
        if cfg.get(key) != value:
            logger.info(f"{prefix} config update: {key}: {cfg.get(key)!r} -> {value!r}")
            cfg[key] = value
            changed = True
            changedKeys.append(key)
    
    if changed and changedKeys:
        _log("info", f"config updated keys: {', '.join(changedKeys)}", prefix)
    
    return changed
