"""Filing rules from ~/.config/pdfFiler/config.json.

A rule names text that must all appear in a PDF and says exactly how to file
it. Rules outrank everything learned from the cabinet (requirement 005,
criterion 3). Example: `pdfFiler/config.example.json`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pdfFiler.dates import STRATEGIES

CONFIG_KEY = "rules"


@dataclass(frozen=True)
class Rule:
    """One filing rule."""

    name: str
    match: tuple[str, ...]
    folder: Path  # relative to the cabinets root
    label: str
    docType: str
    date: str = "default"
    yearSubfolder: bool = False
    nameTemplate: str = "{date} - {label} - {type}.pdf"
    auto: bool = False

    def matches(self, text: str) -> bool:
        """True when every match string appears, ignoring case and spacing."""
        flat = _flatten(text)
        return all(_flatten(item) in flat for item in self.match)


## config


def configDefaultPath() -> Path:
    """The user config path for pdfFiler."""
    return Path.home() / ".config" / "pdfFiler" / "config.json"


def rulesLoad(path: Path) -> list[Rule]:
    """Return the rules in a config file. A missing file has no rules."""
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read {path}: {error}") from error
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must hold a JSON object.")
    items = raw.get(CONFIG_KEY, [])
    if not isinstance(items, list):
        raise ValueError(f"{CONFIG_KEY} in {path} must be a list.")
    return [_ruleParse(item, number) for number, item in enumerate(items, start=1)]


def ruleFind(rules: list[Rule], text: str) -> Rule | None:
    """The first rule whose text matches, or None."""
    return next((rule for rule in rules if rule.matches(text)), None)


## utilities


def _flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _ruleParse(item: object, number: int) -> Rule:
    where = f"rule {number}"
    if not isinstance(item, dict):
        raise ValueError(f"{where} must be a JSON object.")
    for key in ("name", "match", "folder", "label", "type"):
        if key not in item:
            raise ValueError(f"{where} needs '{key}'.")
    match = item["match"]
    if isinstance(match, str):
        match = [match]
    if not match or not all(isinstance(entry, str) and entry.strip() for entry in match):
        raise ValueError(f"{where}: 'match' must be text or a list of text.")
    folder = Path(str(item["folder"]))
    if folder.is_absolute() or ".." in folder.parts:
        raise ValueError(f"{where}: 'folder' must be relative to the cabinets folder.")
    date = item.get("date", "default")
    if date not in STRATEGIES:
        raise ValueError(f"{where}: 'date' must be one of {', '.join(STRATEGIES)}.")
    template = item.get("fileName", "{date} - {label} - {type}.pdf")
    if not str(template).lower().endswith(".pdf") or "{date}" not in str(template):
        raise ValueError(f"{where}: 'fileName' must contain {{date}} and end in .pdf.")
    return Rule(
        name=str(item["name"]),
        match=tuple(match),
        folder=folder,
        label=str(item["label"]),
        docType=str(item["type"]),
        date=date,
        yearSubfolder=bool(item.get("yearSubfolder", False)),
        nameTemplate=str(template),
        auto=bool(item.get("auto", False)),
    )
