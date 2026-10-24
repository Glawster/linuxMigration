"""Exempt show names from the user config file."""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_KEY = "exemptShows"


## config


def configDefaultPath() -> Path:
    """Return the user config path for this application."""
    return Path.home() / ".config" / "suggestUnwatched" / "config.json"


def configLoad(path: Path) -> list[str]:
    """Return exempt show names. A missing file exempts nothing."""
    if not path.is_file():
        return []
    raw = _jsonRead(path)
    if not isinstance(raw, dict):
        raise ValueError("Exempt list must be a JSON object.")
    shows = raw.get(CONFIG_KEY, [])
    if not isinstance(shows, list) or any(not isinstance(item, str) for item in shows):
        raise ValueError("exemptShows must be a list of show names.")
    cleaned = [item.strip() for item in shows]
    if any(not item for item in cleaned):
        raise ValueError("exemptShows entries must be non-empty show names.")
    return cleaned


def configSave(path: Path, exemptShows: list[str]) -> None:
    """Write exempt show names, preserving any other config keys."""
    raw = _existingObject(path)
    raw[CONFIG_KEY] = exemptShows
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        raise ValueError(f"Cannot write exempt list: {error}") from error


def exemptAdd(shows: list[str], name: str) -> list[str]:
    """Append a show name once, ignoring case."""
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Show name must not be empty.")
    if any(item.casefold() == cleaned.casefold() for item in shows):
        return list(shows)
    return [*shows, cleaned]


def exemptRemove(shows: list[str], name: str) -> list[str]:
    """Drop a show name, ignoring case."""
    cleaned = name.strip().casefold()
    return [item for item in shows if item.casefold() != cleaned]


## utilities


def _existingObject(path: Path) -> dict:
    if not path.is_file():
        return {}
    raw = _jsonRead(path)
    if not isinstance(raw, dict):
        raise ValueError("Exempt list must be a JSON object.")
    return dict(raw)


def _jsonRead(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read exempt list: {error}") from error
