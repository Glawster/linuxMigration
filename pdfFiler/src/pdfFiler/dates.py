"""Find a document's date in its text or file name.

Every strategy returns a real calendar date no later than `today`
(requirement 005, criterion 16). A date never comes from inside a longer
token such as the reference `PDOEA02-20260524-21923` (criterion 17).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

STRATEGIES = ("default", "standaloneLine", "statementPeriodEnd", "taxYearEnd")

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip
_MONTH_WORD = (
    r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?"
    r"|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
# Lookarounds keep dates out of longer tokens: no letter, digit, "/", "." or
# "-" may touch the date, except a sentence-ending full stop.
_BEFORE = r"(?<![\w/.-])"
_AFTER = r"(?![\w/-]|\.\d)"
_WRITTEN = re.compile(
    _BEFORE + r"(\d{1,2})(?:st|nd|rd|th)?\s+" + _MONTH_WORD + r",?\s+(\d{4})" + _AFTER,
    re.IGNORECASE,
)
_ISO = re.compile(_BEFORE + r"(\d{4})[-/](\d{2})[-/](\d{2})" + _AFTER)
_NUMERIC = re.compile(_BEFORE + r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})" + _AFTER)


@dataclass(frozen=True)
class DateFound:
    """A valid date found in text, where it starts and how it was written."""

    value: dt.date
    start: int
    kind: str  # "written", "iso" or "numeric"


## strategy


def dateChoose(text: str, strategy: str, today: dt.date) -> dt.date | None:
    """Return the document date by the named strategy, or None.

    Each specialised strategy falls back to "default" when it finds nothing.
    """
    found = datesFind(text, today)
    chosen: dt.date | None = None
    if strategy == "standaloneLine":
        chosen = _standaloneLine(text, found)
    elif strategy == "statementPeriodEnd":
        chosen = _statementPeriodEnd(text, found)
    elif strategy == "taxYearEnd":
        chosen = _taxYearEnd(text, today)
    elif strategy != "default":
        raise ValueError(f"Unknown date strategy: {strategy}")
    return chosen or _default(text, found)


def dateFromFilename(name: str, today: dt.date) -> dt.date | None:
    """Return a date written in a file name (2026-10-30, 20261030, 30-10-2026)."""
    stem = name.rsplit(".", 1)[0]
    patterns = (
        (r"(20\d{2})[-_.](\d{2})[-_.](\d{2})", (1, 2, 3)),
        (r"(20\d{2})(\d{2})(\d{2})", (1, 2, 3)),
        (r"(\d{2})[-_.](\d{2})[-_.](20\d{2})", (3, 2, 1)),
    )
    for pattern, (year, month, day) in patterns:
        for match in re.finditer(pattern, stem):
            value = _dateMake(match.group(year), match.group(month), match.group(day))
            if value and value <= today:
                return value
    return None


def datesFind(text: str, today: dt.date) -> list[DateFound]:
    """Return every valid, not-future date in the text, in text order."""
    found: list[DateFound] = []
    for match in _WRITTEN.finditer(text):
        value = _dateMake(match.group(3), _MONTHS[match.group(2)[:3].lower()], match.group(1))
        if value and value <= today:
            found.append(DateFound(value, match.start(), "written"))
    for match in _ISO.finditer(text):
        value = _dateMake(match.group(1), match.group(2), match.group(3))
        if value and value <= today:
            found.append(DateFound(value, match.start(), "iso"))
    for match in _NUMERIC.finditer(text):
        # UK order: day first.
        value = _dateMake(match.group(3), match.group(2), match.group(1))
        if value and value <= today:
            found.append(DateFound(value, match.start(), "numeric"))
    return sorted(found, key=lambda item: item.start)


## strategies


def _default(text: str, found: list[DateFound]) -> dt.date | None:
    """The 1.4a6 order: a date alone on its line, a labelled date, then the
    first written-month, ISO and UK numeric date."""
    standalone = _standaloneLine(text, found)
    if standalone:
        return standalone
    for item in found:
        if re.search(r"\bdate\b[^\n]{0,30}$", _lineBefore(text, item.start), re.IGNORECASE):
            return item.value
    for kind in ("written", "iso", "numeric"):
        for item in found:
            if item.kind == kind:
                return item.value
    return None


def _standaloneLine(text: str, found: list[DateFound]) -> dt.date | None:
    """The first written-month date that is alone on its line."""
    for item in found:
        if item.kind != "written":
            continue
        lineStart = text.rfind("\n", 0, item.start) + 1
        lineEnd = text.find("\n", item.start)
        line = text[lineStart : lineEnd if lineEnd != -1 else len(text)]
        if _WRITTEN.fullmatch(line.strip()):
            return item.value
    return None


def _statementPeriodEnd(text: str, found: list[DateFound]) -> dt.date | None:
    """The latest date written straight after the word "to" ("for X to Y",
    "Period ... to Y"). Works on each line alone, so OCR splitting or
    reordering the period's lines does not matter."""
    ends = [
        item.value
        for item in found
        if re.search(r"\bto\s+$", _lineBefore(text, item.start), re.IGNORECASE)
    ]
    return max(ends) if ends else None


def _taxYearEnd(text: str, today: dt.date) -> dt.date | None:
    """The end (5 April) of the latest UK tax year the text mentions.

    "6 April 2025" starts the year ending 5 April 2026; "5 April 2026" ends it;
    "2025/26" or "2025-26" names it.
    """
    ends: list[dt.date] = []
    for item in datesFind(text, dt.date.max):
        if (item.value.month, item.value.day) == (4, 6):
            ends.append(dt.date(item.value.year + 1, 4, 5))
        elif (item.value.month, item.value.day) == (4, 5):
            ends.append(item.value)
    for match in re.finditer(r"(?<!\d)(20\d{2})[/-](\d{2})(?!\d)", text):
        start = int(match.group(1))
        if int(match.group(2)) == (start + 1) % 100:
            ends.append(dt.date(start + 1, 4, 5))
    ends = [end for end in ends if end <= today]
    return max(ends) if ends else None


## utilities


def _dateMake(year: str | int, month: str | int, day: str | int) -> dt.date | None:
    try:
        return dt.date(int(year), int(month), int(day))
    except ValueError:
        return None


def _lineBefore(text: str, position: int) -> str:
    """The text from the start of the line up to a position."""
    return text[text.rfind("\n", 0, position) + 1 : position]
