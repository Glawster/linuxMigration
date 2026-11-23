"""The filing form: folder, type, date and label for one PDF.

Core logic behind the filing window, testable without a GUI. The window
shows a FormState, passes the user's changes back through formFolderSet and
formTypeSet, and shows formCheck's result: the full filed name, or what is
wrong with it.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

from pdfFiler.cabinet import CabinetIndex
from pdfFiler.dates import dateChoose, dateFromFilename
from pdfFiler.filing import filingCheck
from pdfFiler.naming import KEEP_ORIGINAL, dateStrategyFor, fileNameBuild, typeChoose, typesOffered
from pdfFiler.suggest import Suggestion

DEFAULT_TEMPLATE = "{date} - {label} - {type}.pdf"


@dataclass
class FormState:
    """What the filing window shows and edits for one PDF."""

    root: Path
    pdf: Path
    text: str
    folder: str  # relative to root; "" until chosen
    folderChoices: list[str]
    docType: str
    typeChoices: list[str]
    date: str  # YYYY-MM-DD as typed
    label: str
    reasons: list[str]
    suggestion: Suggestion | None = None
    # Fields the user typed into are not recalculated behind their back.
    edited: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class FormCheck:
    """The result of checking a form: where it would file, or why not."""

    destination: Path | None
    problem: str | None = None
    outcome: str = "file"  # "file", "duplicate" or "conflict"
    existing: Path | None = None
    shown: str = ""  # folder/name relative to the cabinets root, one line


FILE = "file"
SKIP = "skip"
STOP = "stop"


@dataclass(frozen=True)
class Decision:
    """What the user chose in the filing window."""

    action: str  # FILE, SKIP or STOP
    check: FormCheck | None = None  # the checked form, for FILE


## form


def formCreate(
    pdf: Path,
    text: str,
    suggestion: Suggestion | None,
    index: CabinetIndex,
    today: dt.date,
) -> FormState:
    """Fill the form from a suggestion, or as far as possible without one."""
    if suggestion is not None:
        folders = [str(suggestion.folder)] + [
            str(candidate.folder) for candidate in suggestion.runnerUps
        ]
        info = index.folder(suggestion.folder)
        return FormState(
            root=index.root,
            pdf=pdf,
            text=text,
            folder=str(suggestion.folder),
            folderChoices=_unique(folders),
            docType=suggestion.docType,
            typeChoices=typesOffered(suggestion.docType, info),
            date=suggestion.date.isoformat() if suggestion.date else "",
            label=suggestion.label,
            reasons=list(suggestion.reasons),
            suggestion=suggestion,
        )
    date = dateChoose(text, "default", today) or dateFromFilename(pdf.name, today)
    info = index.folder(Path("."))
    return FormState(
        root=index.root,
        pdf=pdf,
        text=text,
        folder="",
        folderChoices=[],
        docType="Other",
        typeChoices=typesOffered(None, info),
        date=date.isoformat() if date else "",
        label="",
        reasons=["no suggestion: choose a folder"],
    )


def formCheck(state: FormState, today: dt.date) -> FormCheck:
    """Build the destination and say what filing would do, or what is wrong."""
    folder = state.folder.strip().strip("/")
    if not folder:
        return FormCheck(None, "Choose a folder.")
    relative = Path(folder)
    if relative.is_absolute() or ".." in relative.parts:
        return FormCheck(None, "The folder must be inside the cabinets folder.")
    try:
        date = dt.date.fromisoformat(state.date.strip())
    except ValueError:
        return FormCheck(None, "Enter the date as YYYY-MM-DD.")
    if date > today:
        return FormCheck(None, "The date is in the future.")
    label = state.label.strip()
    if not label:
        return FormCheck(None, "Enter a label.")
    docType = state.docType.strip() or "Other"
    namePart = re.sub(r'[\\/:*?"<>|]', "-", state.pdf.stem) if docType == KEEP_ORIGINAL else docType
    name = fileNameBuild(_template(state), date, label, namePart)
    destination = state.root / relative / name
    shown = f"{relative.as_posix()}/{name}"
    check = filingCheck(state.pdf, destination)
    if check.outcome == "conflict":
        problem = "A different file already has this name; change the label, type or date."
        return FormCheck(destination, problem, "conflict", check.existing, shown)
    return FormCheck(destination, None, check.outcome, check.existing, shown)


def formFolderSet(state: FormState, folder: str, index: CabinetIndex, today: dt.date) -> None:
    """Change the folder; recalculate the label, type and date not typed in."""
    state.folder = folder.strip().strip("/")
    relative = Path(state.folder) if state.folder else Path(".")
    info = index.folder(relative)
    sameAsSuggestion = state.suggestion is not None and relative == state.suggestion.folder
    if "label" not in state.edited:
        state.label = state.suggestion.label if sameAsSuggestion else info.labelUsual()
    if "type" not in state.edited:
        docType = (
            state.suggestion.docType if sameAsSuggestion else typeChoose(state.text, info, index)[0]
        )
        formTypeSet(state, docType, today, edited=False)
    state.typeChoices = typesOffered(state.docType, info)


def formTypeSet(state: FormState, docType: str, today: dt.date, edited: bool = True) -> None:
    """Change the type; recalculate the date unless it was typed in."""
    state.docType = docType
    if edited:
        state.edited.add("type")
    if "date" in state.edited:
        return
    date = dateChoose(state.text, dateStrategyFor(docType), today) or dateFromFilename(
        state.pdf.name, today
    )
    if date is not None:
        state.date = date.isoformat()


## utilities


def _template(state: FormState) -> str:
    suggestion = state.suggestion
    if suggestion is not None and Path(state.folder) == suggestion.folder:
        return suggestion.nameTemplate
    return DEFAULT_TEMPLATE


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
