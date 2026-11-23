"""Choose a document's type and date strategy, and build its filed name."""

from __future__ import annotations

import datetime as dt
import re

from pdfFiler.cabinet import CabinetIndex, FolderInfo

STANDARD_TYPES = (
    "Invoice",
    "Statement",
    "Receipt",
    "Policy Documents",
    "P60",
    "Payslip",
    "LetterTo",
    "LetterFrom",
    "Renewal",
    "Certificate of Insurance",
    "Tax",
    "Keep Original Name",
    "Other",
)
KEEP_ORIGINAL = "Keep Original Name"

# Phrases that are evidence for a type, with their weight. More specific
# phrases weigh more, so "certificate of insurance" beats "policy".
_TYPE_EVIDENCE: dict[str, tuple[tuple[str, int], ...]] = {
    "Tax": (
        ("tax certificate", 4),
        ("tax deducted", 4),
        ("tax year", 3),
        ("tax return", 3),
        ("tax", 1),
    ),
    "Statement": (("statement", 1),),
    "Renewal": (("renewal", 2), ("renew", 1)),
    "Policy Documents": (("policy schedule", 3), ("policy document", 3), ("policy wording", 3)),
    "Certificate of Insurance": (("certificate of insurance", 4),),
    "P60": (("p60", 4),),
    "Payslip": (("payslip", 3), ("pay slip", 3)),
    "Invoice": (("invoice", 2),),
    "Receipt": (("receipt", 2),),
}
_DATE_STRATEGY = {"Tax": "taxYearEnd", "Statement": "statementPeriodEnd"}


## naming


def dateStrategyFor(docType: str) -> str:
    """The date strategy for a document type."""
    return _DATE_STRATEGY.get(docType, "default")


def fileNameBuild(template: str, date: dt.date, label: str, docType: str) -> str:
    """Fill a name template ({date}, {label}, {type}, {Mon}, {year})."""
    name = template.format(
        date=date.isoformat(),
        label=label,
        type=docType,
        Mon=date.strftime("%b"),
        year=date.year,
    )
    return re.sub(r'[\\/:*?"<>|]', "-", name)


def typeChoose(text: str, folder: FolderInfo, index: CabinetIndex) -> tuple[str, str]:
    """Return (type, reason) for a document filed in a folder.

    Keyword evidence chooses from the standard types and the types used in
    the cabinet; the folder's own types settle ties. With no evidence the
    folder's most used type is chosen, then "Other".
    """
    candidates = set(STANDARD_TYPES) | set(index.typesAll) | set(folder.types)
    scores = {
        docType: score for docType in candidates if (score := _typeEvidence(text, docType)) > 0
    }
    if scores:
        best = max(scores.values())
        tied = [docType for docType, score in scores.items() if score == best]
        chosen = max(tied, key=lambda docType: (folder.types[docType], docType == "Statement"))
        return chosen, f'type from the words in the letter ("{chosen}")'
    if folder.types:
        chosen = folder.types.most_common(1)[0][0]
        return chosen, "type most used in this folder"
    return "Other", "no type evidence"


def typesOffered(suggested: str | None, folder: FolderInfo) -> list[str]:
    """Types for the type dialog: the suggestion first, then the folder's,
    then the standard list."""
    ordered: list[str] = []
    for docType in (suggested, *[name for name, _ in folder.types.most_common()], *STANDARD_TYPES):
        if docType and docType not in ordered:
            ordered.append(docType)
    return ordered


## utilities


def _typeEvidence(text: str, docType: str) -> int:
    phrases = _TYPE_EVIDENCE.get(docType, ())
    return sum(
        weight * len(re.findall(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE))
        for phrase, weight in phrases
    )
