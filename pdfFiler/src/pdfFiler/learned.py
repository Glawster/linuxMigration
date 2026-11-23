"""Reference numbers learned from confirmed filings (ADR 012).

Stored in ~/.config/pdfFiler/learned.json as
`{"identifiers": {"<NUMBER>": "<folder>"}, "conflicts": [...]}`. Unknown keys
are preserved.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pdfFiler.cabinet import identifiersFind

_LABEL = re.compile(
    r"\b(policy|account|plan|reference|customer|membership|agreement|contract)"
    r"\s*(number|no\.?|ref\.?)?\b",
    re.IGNORECASE,
)
# Lines about the sender's own registration (FCA firm reference, company or
# VAT number) carry the same number on every letter from that sender.
_SENDER_LINE = re.compile(
    r"\b(firm|registered|registration|company|authority|authorised|vat|charity)\b",
    re.IGNORECASE,
)
_LONG_MIXED = re.compile(r"(?<![A-Z0-9])(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{10,}(?![A-Z0-9])")


@dataclass
class Learned:
    """Numbers learned from confirmations, and numbers seen for two folders."""

    identifiers: dict[str, Path] = field(default_factory=dict)
    conflicts: list[dict[str, object]] = field(default_factory=list)


## learned


def learnedDefaultPath() -> Path:
    return Path.home() / ".config" / "pdfFiler" / "learned.json"


def learnedLoad(path: Path) -> Learned:
    """Read learned numbers. A missing file has none."""
    raw = _objectRead(path)
    identifiers = raw.get("identifiers", {})
    conflicts = raw.get("conflicts", [])
    if not isinstance(identifiers, dict) or not isinstance(conflicts, list):
        raise ValueError(f"{path}: 'identifiers' must be an object and 'conflicts' a list.")
    return Learned(
        identifiers={str(key).upper(): Path(str(value)) for key, value in identifiers.items()},
        conflicts=conflicts,
    )


def learnedNumbersFind(text: str) -> set[str]:
    """Reference numbers worth remembering from a PDF being filed.

    Identifier tokens on the same line as a label ("Policy Number",
    "Account number", "Plan", "Reference", ...) except lines about the
    sender's registration, and letter-and-digit tokens
    of ten or more characters that appear at least twice, because OCR often
    moves a number away from its label.
    """
    numbers: set[str] = set()
    for line in text.splitlines():
        if _LABEL.search(line) and not _SENDER_LINE.search(line):
            numbers |= identifiersFind(_LABEL.sub(" ", line))
    counts = Counter(_LONG_MIXED.findall(text.upper()))
    numbers |= {token for token, count in counts.items() if count >= 2}
    return numbers


def learnedRecord(path: Path, numbers: set[str], folder: Path) -> tuple[list[str], list[str]]:
    """Save numbers against a folder; return (added, conflicting).

    A number already saved for a different folder is left as it is and the
    conflict is recorded once.
    """
    raw = _objectRead(path)
    learned = learnedLoad(path)
    added: list[str] = []
    conflicting: list[str] = []
    for number in sorted(numbers):
        existing = learned.identifiers.get(number)
        if existing is None:
            learned.identifiers[number] = folder
            added.append(number)
        elif existing != folder:
            conflicting.append(number)
            entry = {"identifier": number, "folders": [str(existing), str(folder)]}
            if entry not in learned.conflicts:
                learned.conflicts.append(entry)
    if added or conflicting:
        raw["identifiers"] = {key: str(value) for key, value in sorted(learned.identifiers.items())}
        raw["conflicts"] = learned.conflicts
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
    return added, conflicting


## utilities


def _objectRead(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read {path}: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must hold a JSON object.")
    return raw
