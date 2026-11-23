"""Suggest where an inbox PDF is filed (requirement 005).

Evidence, strongest first:
  1. a rule from config.json (criterion 3);
  2. an identifier from the cabinet's names or from learned.json
     (criteria 1 and 14);
  3. a folder's name as a word in the text, with the rest of its path
     settling ties between folders of the same name (criteria 2 and 13).
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from pdfFiler.cabinet import CabinetIndex, identifiersFind
from pdfFiler.dates import dateChoose, dateFromFilename
from pdfFiler.learned import Learned
from pdfFiler.naming import dateStrategyFor, fileNameBuild, typeChoose
from pdfFiler.rules import Rule, ruleFind

RULE_SCORE = 1000
IDENTIFIER_SCORE = 100
NAME_SCORE = 10
PATH_WORD_SCORE = 3
KEYWORD_SCORE = 1
# A folder name used by this many folders (people such as "Andy" or "Kathy")
# is too ambiguous to be evidence on its own.
AMBIGUOUS_NAME_FOLDERS = 3

# Folder names too common in letters to be evidence on their own.
_GENERIC_NAMES = {
    "archive", "bills", "documents", "home", "inbox", "letters", "misc",
    "other", "receipts", "statements", "tax", "taxes",
}  # fmt: skip
# Words that point to a folder through one of its ancestors, beyond the
# ancestor's own name ("policy" points to Insurance/...).
_PATH_KEYWORDS = {"insurance": ("policy", "cover", "premium", "insurer")}
_YEAR = re.compile(r"^(19|20)\d{2}$")


@dataclass
class Candidate:
    """A folder and the evidence for it."""

    folder: Path
    score: int = 0
    reasons: list[str] = field(default_factory=list)


@dataclass
class Suggestion:
    """Where and how to file one PDF."""

    folder: Path  # relative to the cabinets root
    label: str
    docType: str
    date: dt.date | None
    reasons: list[str]
    runnerUps: list[Candidate] = field(default_factory=list)
    rule: Rule | None = None
    nameTemplate: str = "{date} - {label} - {type}.pdf"

    def fileName(self) -> str | None:
        """The filed name, or None while the date is unknown."""
        if self.date is None:
            return None
        return fileNameBuild(self.nameTemplate, self.date, self.label, self.docType)

    def reasonText(self) -> str:
        return "; ".join(self.reasons)


## suggestion


def candidatesRank(text: str, index: CabinetIndex, learned: Learned) -> list[Candidate]:
    """Score every folder the text points to, best first.

    Ties go to the folder with more filed PDFs.
    """
    candidates: dict[Path, Candidate] = {}

    def add(folder: Path, score: int, reason: str) -> None:
        candidate = candidates.setdefault(folder, Candidate(folder))
        candidate.score += score
        if reason not in candidate.reasons:
            candidate.reasons.append(reason)

    for identifier in sorted(identifiersFind(text)):
        for folder in index.identifiers.get(identifier, {}):
            add(folder, IDENTIFIER_SCORE, f"matched {identifier}")
        if identifier in learned.identifiers:
            add(
                learned.identifiers[identifier],
                IDENTIFIER_SCORE,
                f"matched learned number {identifier}",
            )

    textFold = text.casefold()
    nameCounts = Counter(folder.name for folder in index.folders)
    for folder in index.folders:
        if nameCounts[folder.name] >= AMBIGUOUS_NAME_FOLDERS:
            continue
        # Cheap containment check first; the word match only runs on the few
        # folders whose name appears somewhere in the text.
        if folder.name.casefold() not in textFold:
            continue
        score, reason = _nameEvidence(text, folder)
        if score:
            add(folder, score, reason)

    return sorted(
        candidates.values(),
        key=lambda candidate: (
            -candidate.score,
            -index.folder(candidate.folder).files,
            str(candidate.folder),
        ),
    )


def suggestionMake(
    text: str,
    pdfName: str,
    index: CabinetIndex,
    learned: Learned,
    rules: list[Rule],
    today: dt.date,
) -> Suggestion | None:
    """Suggest the folder, label, type and date for a PDF, or None."""
    ranked = candidatesRank(text, index, learned)
    rule = ruleFind(rules, text)
    if rule is not None:
        date = dateChoose(text, rule.date, today) or dateFromFilename(pdfName, today)
        folder = rule.folder / str(date.year) if rule.yearSubfolder and date else rule.folder
        return Suggestion(
            folder=folder,
            label=rule.label,
            docType=rule.docType,
            date=date,
            reasons=[f"rule: {rule.name}"],
            runnerUps=ranked[:2],
            rule=rule,
            nameTemplate=rule.nameTemplate,
        )
    if not ranked:
        return None
    best = ranked[0]
    info = index.folder(best.folder)
    docType, typeReason = typeChoose(text, info, index)
    date = dateChoose(text, dateStrategyFor(docType), today) or dateFromFilename(pdfName, today)
    return Suggestion(
        folder=best.folder,
        label=info.labelUsual(),
        docType=docType,
        date=date,
        reasons=[*best.reasons, typeReason],
        runnerUps=ranked[1:3],
    )


## utilities


def _nameEvidence(text: str, folder: Path) -> tuple[int, str]:
    """Score a folder whose own name is a word in the text.

    Each ancestor whose name, or one of its keywords, is also in the text
    adds a little, so Insurance/MBNA beats Finance/MBNA for an insurance
    letter.
    """
    name = folder.name
    # A folder name is a proper noun (Aviva, MBNA): it must start with a
    # capital and appear as written or in capitals, so ordinary words in a
    # letter ("basic", "about") do not count.
    if _YEAR.match(name) or len(name) < 3 or not name[0].isupper():
        return 0, ""
    if name.casefold() in _GENERIC_NAMES:
        return 0, ""
    if not (
        _wordIn(name, text, caseSensitive=True) or _wordIn(name.upper(), text, caseSensitive=True)
    ):
        return 0, ""
    score = NAME_SCORE
    words = [name]
    for ancestor in folder.parent.parts:
        if _wordIn(ancestor, text):
            score += PATH_WORD_SCORE
            words.append(ancestor.casefold())
        for keyword in _PATH_KEYWORDS.get(ancestor.casefold(), ()):
            if _wordIn(keyword, text):
                score += KEYWORD_SCORE
                words.append(keyword)
    quoted = " + ".join(f'"{word}"' for word in words)
    return score, f"the letter mentions {quoted}"


def _wordIn(phrase: str, text: str, caseSensitive: bool = False) -> bool:
    flags = 0 if caseSensitive else re.IGNORECASE
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, flags) is not None
