"""`inbox file`: show each inbox PDF in the filing window, then file it.

This module joins the core (suggestions, form, filing) to the GUI. The
window is passed in, so tests can replace it; it needs only
`decide(state, position, total) -> Decision` and `message(kind, text)`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from pdfFiler.cabinet import CabinetIndex, cabinetIndexBuild
from pdfFiler.filing import FilingError, filingCheck, filingMove, filingTrash, inboxList
from pdfFiler.form import FILE, SKIP, STOP, Decision, FormState, formCreate
from pdfFiler.learned import Learned, learnedLoad, learnedNumbersFind, learnedRecord
from pdfFiler.rules import Rule, rulesLoad
from pdfFiler.suggest import Suggestion, suggestionMake
from pdfFiler.text import textOfPdf


class Window(Protocol):
    """What `inbox file` needs from the filing window."""

    def decide(self, state: FormState, position: int, total: int) -> Decision: ...

    def message(self, kind: str, text: str) -> None: ...


@dataclass
class Options:
    """Settings for one `inbox file` run."""

    root: Path
    inbox: Path
    configPath: Path
    learnedPath: Path
    today: dt.date = field(default_factory=dt.date.today)


@dataclass
class Counts:
    filed: int = 0
    duplicates: int = 0
    conflicts: int = 0
    skipped: int = 0
    learned: int = 0
    cancelled: bool = False


## inbox


def inboxIndex(options: Options) -> CabinetIndex:
    """The cabinet index for a run (the window needs it too)."""
    return cabinetIndexBuild(options.root)


def inboxFile(
    options: Options, logger, window: Window, index: CabinetIndex | None = None
) -> Counts:
    """File every inbox PDF, oldest first. The list is taken once, so a PDF
    the user skips is not offered again in the same run."""
    run = _InboxRun(options, logger, window, index or inboxIndex(options))
    return run.all()


class _InboxRun:
    def __init__(self, options: Options, logger, window: Window, index: CabinetIndex) -> None:
        self.options = options
        self.logger = logger
        self.window = window
        self.counts = Counts()
        self.index = index
        self.rules: list[Rule] = rulesLoad(options.configPath)
        self.learned: Learned = learnedLoad(options.learnedPath)

    def all(self) -> Counts:
        pdfs = inboxList(self.options.inbox)
        self.logger.value("pdfs in inbox", len(pdfs))
        for position, pdf in enumerate(pdfs, start=1):
            if not self.one(pdf, position, len(pdfs)):
                self.counts.cancelled = True
                self.logger.info("stopped by user")
                break
        return self.counts

    ## one pdf

    def one(self, pdf: Path, position: int, total: int) -> bool:
        """File one PDF; False when the user stops the run."""
        self.logger.value("pdf", pdf.name)
        text = textOfPdf(pdf)
        suggestion = suggestionMake(
            text, pdf.name, self.index, self.learned, self.rules, self.options.today
        )
        if suggestion is not None:
            self.logger.info(
                "suggested %s because %s",
                f"{suggestion.folder}/{suggestion.fileName() or '(date unknown)'}",
                suggestion.reasonText(),
            )

        # A sure rule files without the window. Skip is not offered.
        if suggestion and suggestion.rule and suggestion.rule.auto and suggestion.date:
            self.logger.info("auto rule %s", suggestion.rule.name)
            self._place(pdf, self._destination(suggestion), text, quiet=True)
            return True

        state = formCreate(pdf, text, suggestion, self.index, self.options.today)
        decision = self.window.decide(state, position, total)
        if decision.action == STOP:
            return False
        if decision.action == SKIP:
            self.logger.info("skipped, left in inbox: %s", pdf.name)
            self.counts.skipped += 1
            return True
        assert decision.action == FILE and decision.check and decision.check.destination
        self._place(pdf, decision.check.destination, text)
        return True

    ## filing

    def _place(self, pdf: Path, destination: Path, text: str, quiet: bool = False) -> None:
        """File, trash as already filed, or leave because the name is taken."""
        folder = destination.parent.relative_to(self.options.root)
        check = filingCheck(pdf, destination)
        if check.outcome == "duplicate":
            self.logger.action(f"trash {pdf.name}: already filed as {check.existing.name}")
            filingTrash(pdf)
            self.counts.duplicates += 1
            return
        if check.outcome == "conflict":
            if not quiet:
                self.window.message(
                    "error",
                    f"A different file already exists:\n{destination}\n\n{pdf.name} stays in the inbox.",
                )
            self.logger.warning(
                "%s already exists with different content; left in inbox: %s",
                destination.name,
                pdf.name,
            )
            self.counts.conflicts += 1
            return
        self.logger.action(f"move {pdf.name} → {folder.as_posix()}/{destination.name}")
        try:
            filingMove(pdf, destination)
        except FilingError as error:
            self.logger.error(str(error))
            raise SystemExit(1) from None
        self.counts.filed += 1
        self._learn(text, folder)

    def _learn(self, text: str, folder: Path) -> None:
        """Remember this PDF's reference numbers against its folder (ADR 012)."""
        added, conflicting = learnedRecord(
            self.options.learnedPath, learnedNumbersFind(text), folder
        )
        for number in added:
            self.learned.identifiers[number] = folder
            self.logger.info("learned %s for %s", number, folder)
        for number in conflicting:
            self.logger.warning("%s is already learned for another folder, not %s", number, folder)
        self.counts.learned += len(added)

    ## utilities

    def _destination(self, suggestion: Suggestion) -> Path:
        return self.options.root / suggestion.folder / suggestion.fileName()
