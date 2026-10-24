"""Oldest episode air dates from Media Center Master XML."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import re

_FIRST_AIRED = re.compile(
    r"<FirstAired>\s*([^<\s]+)\s*</FirstAired>",
    re.IGNORECASE,
)
_MIN_YEAR = 1900
_MAX_YEAR = 2100


## airdate


def airdateOldest(folder: Path, root: Path) -> date | None:
    """Return the oldest MCM FirstAired date for a video folder."""
    found = _datesInFolder(folder)
    if found:
        return min(found)
    return _seriesDate(folder, root)


def airdateParse(value: str) -> date | None:
    """Parse an MCM FirstAired value, rejecting placeholder dates."""
    parsed = _dateParse(value.strip())
    if parsed is None or not _MIN_YEAR <= parsed.year <= _MAX_YEAR:
        return None
    return parsed


## utilities


def _dateParse(value: str) -> date | None:
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value[:10], pattern).date()
        except ValueError:
            continue
    return None


def _datesInFolder(folder: Path) -> list[date]:
    dates: list[date] = []
    for path in _xmlPaths(folder):
        parsed = _xmlDate(path)
        if parsed is not None:
            dates.append(parsed)
    return dates


def _seriesDate(folder: Path, root: Path) -> date | None:
    current = folder.absolute()
    stop = root.absolute()
    while True:
        parsed = _xmlDate(current / "series.xml")
        if parsed is not None:
            return parsed
        if current == stop or current.parent == current:
            return None
        current = current.parent


def _xmlDate(path: Path) -> date | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    match = _FIRST_AIRED.search(text)
    if match is None:
        return None
    return airdateParse(match.group(1))


def _xmlPaths(folder: Path) -> list[Path]:
    paths = [path for path in folder.glob("*.xml") if path.is_file()]
    metadata = folder / "metadata"
    if metadata.is_dir():
        paths.extend(path for path in metadata.glob("*.xml") if path.is_file())
    return paths
