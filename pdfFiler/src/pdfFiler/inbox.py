"""`inbox file`: offer each inbox PDF with a suggestion, then file it.

This module joins the core (suggestions, filing) to the GUI (dialogs,
preview). Dialogs and preview are passed in, so tests can replace them.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path

from pdfFiler.cabinet import CabinetIndex, cabinetIndexBuild
from pdfFiler.dates import dateChoose, dateFromFilename
from pdfFiler.dialogs import CHANGE, FILE, SKIP, Dialogs
from pdfFiler.filing import FilingError, filingCheck, filingMove, filingTrash, inboxList
from pdfFiler.learned import Learned, learnedLoad, learnedNumbersFind, learnedRecord
from pdfFiler.naming import KEEP_ORIGINAL, dateStrategyFor, fileNameBuild, typeChoose, typesOffered
from pdfFiler.preview import Preview
from pdfFiler.rules import Rule, rulesLoad
from pdfFiler.suggest import Suggestion, suggestionMake
from pdfFiler.text import textOfPdf

DEFAULT_TEMPLATE = "{date} - {label} - {type}.pdf"
_PREVIEW_NOTE = "\n\n(Preview: nothing will move. Run with --confirm to file.)"


@dataclass
class Options:
    """Settings for one `inbox file` run."""

    root: Path
    inbox: Path
    dryRun: bool
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


class _Stop(Exception):
    """The user cancelled the run."""


## inbox


def inboxFile(options: Options, logger, dialogs: Dialogs, preview: Preview) -> Counts:
    """File every inbox PDF, oldest first. The list is taken once, so a PDF
    the user skips is not offered again in the same run."""
    run = _InboxRun(options, logger, dialogs, preview)
    return run.all()


class _InboxRun:
    def __init__(self, options: Options, logger, dialogs: Dialogs, preview: Preview) -> None:
        self.options = options
        self.logger = logger
        self.dialogs = dialogs
        self.preview = preview
        self.counts = Counts()
        self.index: CabinetIndex = cabinetIndexBuild(options.root)
        self.rules: list[Rule] = rulesLoad(options.configPath)
        self.learned: Learned = learnedLoad(options.learnedPath)

    def all(self) -> Counts:
        pdfs = inboxList(self.options.inbox)
        self.logger.value("pdfs in inbox", len(pdfs))
        try:
            for pdf in pdfs:
                try:
                    self.one(pdf)
                finally:
                    self.preview.close()
        except _Stop:
            self.counts.cancelled = True
            self.logger.info("cancelled by user")
        return self.counts

    ## one pdf

    def one(self, pdf: Path) -> None:
        self.logger.value("pdf", pdf.name)
        text = textOfPdf(pdf)
        suggestion = suggestionMake(
            text, pdf.name, self.index, self.learned, self.rules, self.options.today
        )
        if suggestion is not None:
            self.logger.info(
                "suggested %s because %s",
                self._shown(suggestion.folder, suggestion.fileName()),
                suggestion.reasonText(),
            )

        # A sure rule files without dialogs, and only with --confirm.
        if suggestion and suggestion.rule and suggestion.rule.auto and suggestion.date:
            if self.options.dryRun:
                self.logger.info("auto rule %s: preview only", suggestion.rule.name)
            self._place(pdf, self._destination(suggestion), text, suggestion.folder, quiet=True)
            return

        if not self.preview.show(pdf):
            self.dialogs.message("warning", f"Preview could not be generated for {pdf.name}")

        if suggestion is not None and suggestion.date is not None:
            answer = self.dialogs.suggestionAsk(self._suggestionText(pdf, suggestion))
            if answer == FILE:
                self._place(pdf, self._destination(suggestion), text, suggestion.folder)
                return
            if answer == SKIP:
                self.logger.info("skipped, left in inbox: %s", pdf.name)
                self.counts.skipped += 1
                return
            assert answer == CHANGE
        self._manual(pdf, text, suggestion)

    def _manual(self, pdf: Path, text: str, suggestion: Suggestion | None) -> None:
        """The 1.4a6 dialogs, filled in with the suggestion where there is one."""
        start = self.options.root
        if suggestion and (self.options.root / suggestion.folder).is_dir():
            start = self.options.root / suggestion.folder
        chosen = self.dialogs.folderChoose(start)
        if chosen is None:
            raise _Stop
        chosen = chosen.resolve()
        root = self.options.root.resolve()
        if root not in chosen.parents:
            self.dialogs.message("error", f"Folder must be inside {root}")
            self.logger.warning("folder outside cabinets, left in inbox: %s", pdf.name)
            self.counts.skipped += 1
            return
        relative = chosen.relative_to(root)
        info = self.index.folder(relative)
        sameFolder = suggestion is not None and relative == suggestion.folder

        suggestedType = suggestion.docType if sameFolder else typeChoose(text, info, self.index)[0]
        docType = self.dialogs.typeChoose(pdf.name, typesOffered(suggestedType, info))
        if docType is None:
            raise _Stop
        label = suggestion.label if sameFolder else info.labelUsual()
        namePart = re.sub(r'[\\/:*?"<>|]', "-", pdf.stem) if docType == KEEP_ORIGINAL else docType

        date = None
        if sameFolder and docType == suggestion.docType:
            date = suggestion.date
        date = date or dateChoose(text, dateStrategyFor(docType), self.options.today)
        date = date or dateFromFilename(pdf.name, self.options.today)
        date = date or self._dateAsk()

        template = suggestion.nameTemplate if sameFolder else DEFAULT_TEMPLATE
        destination = chosen / fileNameBuild(template, date, label, namePart)
        question = f"File:\n{pdf.name}\n\nAs:\n{destination}\n\nProceed?"
        if not self.dialogs.proceedAsk(question + (_PREVIEW_NOTE if self.options.dryRun else "")):
            self.logger.info("declined, left in inbox: %s", pdf.name)
            self.counts.skipped += 1
            return
        self._place(pdf, destination, text, relative)

    ## filing

    def _place(
        self, pdf: Path, destination: Path, text: str, folder: Path, quiet: bool = False
    ) -> None:
        """File, trash as already filed, or leave because the name is taken."""
        check = filingCheck(pdf, destination)
        if check.outcome == "duplicate":
            self.logger.action(f"trash {pdf.name}: already filed as {check.existing.name}")
            if not self.options.dryRun:
                filingTrash(pdf)
            self.counts.duplicates += 1
            return
        if check.outcome == "conflict":
            if not quiet:
                self.dialogs.message(
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
        self.logger.action(f"move {pdf.name} → {self._shown(folder, destination.name)}")
        if self.options.dryRun:
            self.counts.filed += 1
            return
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

    def _dateAsk(self) -> dt.date:
        problem = "No date found in the PDF or its name."
        while True:
            entered = self.dialogs.dateAsk(problem=problem)
            if entered is None:
                raise _Stop
            try:
                value = dt.date.fromisoformat(entered)
            except ValueError:
                problem = f"'{entered}' is not a valid date."
                continue
            if value > self.options.today:
                problem = f"{entered} is in the future."
                continue
            return value

    def _destination(self, suggestion: Suggestion) -> Path:
        return self.options.root / suggestion.folder / suggestion.fileName()

    def _shown(self, folder: Path, name: str | None) -> str:
        return f"{folder}/{name}" if name else f"{folder}/(date unknown)"

    def _suggestionText(self, pdf: Path, suggestion: Suggestion) -> str:
        lines = [
            f"File:\n{pdf.name}",
            f"As:\n{suggestion.folder}/{suggestion.fileName()}",
            f"Because:\n{suggestion.reasonText()}",
        ]
        if suggestion.runnerUps:
            others = ", ".join(str(candidate.folder) for candidate in suggestion.runnerUps)
            lines.append(f"Other folders (Change…):\n{others}")
        text = "\n\n".join(lines)
        return text + (_PREVIEW_NOTE if self.options.dryRun else "")
