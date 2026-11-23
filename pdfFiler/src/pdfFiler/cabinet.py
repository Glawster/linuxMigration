"""Learn the cabinet from its folder and file names (ADR 012).

No filed PDF is opened. Filed names follow
`<yyyy-mm-dd> - <label> - <type>[ - <Mon>].pdf`; folder names and labels may
contain identifiers such as `AV2550339`.
"""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

SKIPPED_TOP_FOLDERS = {"Inbox", "Archive"}

_IDENTIFIER = re.compile(r"(?<![A-Z0-9])(?=[A-Z0-9]*\d)[A-Z0-9]{6,}(?![A-Z0-9])")
_FILED_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\s*-?\s*(.*)$")
_MONTH_SUFFIX = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$")
_COPY_SUFFIX = re.compile(r"\s*(\(\d+\)|\d{1,2})$")
_YEAR = re.compile(r"^(19|20)\d{2}$")


@dataclass
class FolderInfo:
    """What the names in one folder say."""

    path: Path  # relative to the cabinets root
    files: int = 0
    labels: Counter[str] = field(default_factory=Counter)
    types: Counter[str] = field(default_factory=Counter)

    def labelUsual(self) -> str:
        """The folder's most used label, or its name (its parent's for a year)."""
        if self.labels:
            return self.labels.most_common(1)[0][0]
        return folderLabel(self.path)


@dataclass
class CabinetIndex:
    """Identifiers, labels and types learned from the cabinet's names."""

    root: Path
    folders: dict[Path, FolderInfo] = field(default_factory=dict)
    identifiers: dict[str, Counter[Path]] = field(default_factory=dict)
    typesAll: Counter[str] = field(default_factory=Counter)

    def folder(self, path: Path) -> FolderInfo:
        """The info for a folder, empty when nothing is known about it."""
        return self.folders.get(path) or FolderInfo(path)

    def identifierAdd(self, identifier: str, folder: Path, weight: int = 1) -> None:
        self.identifiers.setdefault(identifier.upper(), Counter())[folder] += weight


## cabinet


def cabinetIndexBuild(root: Path) -> CabinetIndex:
    """Walk the cabinets root and learn from names only.

    `Inbox` and `Archive` directly under the root, and hidden folders, are
    skipped.
    """
    index = CabinetIndex(root)
    for current, dirNames, fileNames in os.walk(root):
        currentPath = Path(current)
        relative = currentPath.relative_to(root)
        dirNames[:] = sorted(
            name
            for name in dirNames
            if not name.startswith(".")
            and not (relative == Path(".") and name in SKIPPED_TOP_FOLDERS)
        )
        if relative != Path("."):
            info = index.folders.setdefault(relative, FolderInfo(relative))
            for identifier in identifiersFind(relative.name):
                index.identifierAdd(identifier, relative, weight=5)
        else:
            info = FolderInfo(relative)
        for name in fileNames:
            if not name.lower().endswith(".pdf"):
                continue
            info.files += 1
            parsed = filedNameParse(name)
            if parsed is None:
                continue
            label, docType = parsed
            info.labels[label] += 1
            if docType:
                info.types[docType] += 1
                index.typesAll[docType] += 1
            if relative != Path("."):
                for identifier in identifiersFind(label):
                    index.identifierAdd(identifier, relative)
    return index


def filedNameParse(name: str) -> tuple[str, str | None] | None:
    """Return (label, type) from `<date> - <label> - <type>[ - <Mon>].pdf`.

    Copy suffixes (" 1", " (2)") are dropped. Returns None for names that do
    not start with a date.
    """
    stem = name.rsplit(".", 1)[0]
    match = _FILED_NAME.match(stem)
    if not match or not match.group(2).strip():
        return None
    parts = [part.strip() for part in match.group(2).split(" - ") if part.strip()]
    if len(parts) > 2 and _MONTH_SUFFIX.match(parts[-1]):
        parts = parts[:-1]
    parts[-1] = _COPY_SUFFIX.sub("", parts[-1]).strip() or parts[-1]
    label = parts[0]
    docType = " - ".join(parts[1:]) if len(parts) > 1 else None
    return label, docType


def folderLabel(path: Path) -> str:
    """A folder's own name, or its parent's when the folder is a year."""
    if _YEAR.match(path.name) and path.parent.name:
        return path.parent.name
    return path.name


def identifiersFind(text: str) -> set[str]:
    """Tokens of six or more letters and digits containing a digit."""
    return set(_IDENTIFIER.findall(text.upper()))
