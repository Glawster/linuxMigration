"""The `inbox file` workflow (criteria 7-10 and the 1.4a6 safety rules).

Dialogs and preview are scripted stand-ins; text, suggestions, filing,
learning and the gio double are real.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from conftest import AVIVA_ISA_LINES, AVIVA_TAX_LINES, MBNA_RENEWAL_LINES, TODAY

from pdfFiler.dialogs import CHANGE, FILE, SKIP
from pdfFiler.inbox import Options, inboxFile
from pdfFiler.learned import learnedLoad

EXAMPLE_CONFIG = Path(__file__).resolve().parents[1] / "config.example.json"


class FakeDialogs:
    """Answers from a script and records every question."""

    def __init__(self, **answers) -> None:
        self.answers = answers
        self.asked: list[tuple] = []

    def _answer(self, name: str, *details):
        self.asked.append((name, *details))
        value = self.answers.get(name)
        return value.pop(0) if isinstance(value, list) else value

    def suggestionAsk(self, text: str) -> str:
        return self._answer("suggestionAsk", text) or FILE

    def folderChoose(self, start: Path):
        return self._answer("folderChoose", start)

    def typeChoose(self, pdfName: str, types: list[str]):
        answer = self._answer("typeChoose", types)
        return answer if answer is not None else types[0]

    def dateAsk(self, prefill: str = "", problem: str = ""):
        return self._answer("dateAsk", problem)

    def proceedAsk(self, text: str) -> bool:
        answer = self._answer("proceedAsk", text)
        return True if answer is None else answer

    def message(self, kind: str, text: str) -> None:
        self.asked.append(("message", kind, text))

    def names(self) -> list[str]:
        return [entry[0] for entry in self.asked]


class FakePreview:
    def show(self, pdf: Path) -> bool:
        return True

    def close(self) -> None:
        pass


class FakeLogger:
    """Collects log lines, like the organiseMyProjects adapter."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def value(self, name, value):
        self.lines.append(f"value: {name}: {value}")

    def __getattr__(self, level):
        def log(message, *args):
            self.lines.append(f"{level}: {message % args if args else message}")

        return log


def _run(cabinet: Path, tmp_path: Path, dialogs: FakeDialogs, confirm: bool = True, config=None):
    options = Options(
        root=cabinet,
        inbox=cabinet / "Inbox",
        dryRun=not confirm,
        configPath=config or tmp_path / "no-config.json",
        learnedPath=tmp_path / "learned.json",
        today=TODAY,
    )
    logger = FakeLogger()
    counts = inboxFile(options, logger, dialogs, FakePreview())
    return counts, logger


## suggestions


def test_fileAcceptsSuggestionWithOneDialog(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    # criterion 7: one dialog, File files it
    pdf = inboxPdf("2026-11-23.pdf", AVIVA_TAX_LINES)
    dialogs = FakeDialogs(suggestionAsk=[FILE])

    counts, _ = _run(cabinet, tmp_path, dialogs)

    filed = cabinet / "Finance/Aviva/AV1111111/2026-04-05 - Aviva, AV1111111 - Tax.pdf"
    assert counts.filed == 1 and filed.is_file() and not pdf.exists()
    assert dialogs.names() == ["suggestionAsk"]
    assert "Because:\nmatched AV1111111" in dialogs.asked[0][1]


def test_changeOpensDialogsFilledWithSuggestion(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    # criterion 7: Change… starts in the suggested folder, suggested type first
    inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)
    dialogs = FakeDialogs(
        suggestionAsk=[CHANGE],
        folderChoose=[cabinet / "Insurance" / "MBNA"],
    )

    counts, _ = _run(cabinet, tmp_path, dialogs)

    assert dialogs.asked[1] == ("folderChoose", cabinet / "Insurance" / "MBNA")
    assert dialogs.asked[2][1][0] == "Renewal"
    assert counts.filed == 1
    assert (cabinet / "Insurance/MBNA/2025-10-20 - Insurance, MBNA - Renewal.pdf").is_file()


def test_changeToAnotherFolderUsesThatFoldersLabel(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)
    dialogs = FakeDialogs(
        suggestionAsk=[CHANGE],
        folderChoose=[cabinet / "Finance" / "MBNA"],
        typeChoose=["Letter From"],
    )

    _run(cabinet, tmp_path, dialogs)

    assert (cabinet / "Finance/MBNA/2025-10-20 - MBNA - Letter From.pdf").is_file()


def test_skipLeavesPdfAndMovesOn(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    first = inboxPdf("a.pdf", AVIVA_TAX_LINES)
    second = inboxPdf("b.pdf", AVIVA_ISA_LINES)
    dialogs = FakeDialogs(suggestionAsk=[SKIP, SKIP])

    counts, _ = _run(cabinet, tmp_path, dialogs)

    assert counts.skipped == 2 and first.exists() and second.exists()
    assert dialogs.names() == ["suggestionAsk", "suggestionAsk"]


def test_noSuggestionShowsTheOldDialogs(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    # criterion 9: folder, type, date and proceed, as in 1.4a6
    (cabinet / "Taxes").mkdir()
    inboxPdf("scan.pdf", ["A letter with nothing to go on"])
    dialogs = FakeDialogs(
        folderChoose=[cabinet / "Taxes"], typeChoose=["Invoice"], dateAsk=["2026-02-01"]
    )

    counts, _ = _run(cabinet, tmp_path, dialogs)

    assert dialogs.names() == ["folderChoose", "typeChoose", "dateAsk", "proceedAsk"]
    assert dialogs.asked[0][1] == cabinet
    assert (cabinet / "Taxes/2026-02-01 - Taxes - Invoice.pdf").is_file()


def test_invalidAndFutureDatesAreAskedAgain(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    (cabinet / "Taxes").mkdir()
    inboxPdf("scan.pdf", ["nothing"])
    dialogs = FakeDialogs(
        folderChoose=[cabinet / "Taxes"],
        typeChoose=["Invoice"],
        dateAsk=["2026-02-30", "2027-01-01", "2026-02-01"],
    )

    _run(cabinet, tmp_path, dialogs)

    problems = [entry[1] for entry in dialogs.asked if entry[0] == "dateAsk"]
    assert "not a valid date" in problems[1] and "in the future" in problems[2]
    assert (cabinet / "Taxes/2026-02-01 - Taxes - Invoice.pdf").is_file()


def test_cancellingStopsTheRun(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    inboxPdf("a.pdf", ["nothing"])
    inboxPdf("b.pdf", ["nothing"])
    dialogs = FakeDialogs(folderChoose=[None])

    counts, logger = _run(cabinet, tmp_path, dialogs)

    assert counts.cancelled and dialogs.names() == ["folderChoose"]
    assert "info: cancelled by user" in logger.lines


def test_folderOutsideCabinetsIsRefused(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    pdf = inboxPdf("scan.pdf", ["nothing"])

    counts, _ = _run(cabinet, tmp_path, FakeDialogs(folderChoose=[outside]))

    assert counts.skipped == 1 and pdf.exists() and not list(outside.iterdir())


## rules


def _autoConfig(tmp_path: Path) -> Path:
    raw = json.loads(EXAMPLE_CONFIG.read_text())
    raw["rules"][0]["auto"] = True
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw))
    return path


_DP_LINES = [
    "Danske Bank",
    "30 October 2026",
    "Account number: 950246 60153699",
    "Period this statement relates to: 01 October 2026 to 30 October 2026",
]


def test_autoRuleFilesWithoutDialogsOnlyWithConfirm(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    # criterion 8
    pdf = inboxPdf("Statement 950246 60153699.PDF", _DP_LINES)
    target = (
        cabinet / "Benefits/Bank Statements/2026/2026-10-30 - Direct Payments - Statement - Oct.pdf"
    )

    preview = FakeDialogs()
    _run(cabinet, tmp_path, preview, confirm=False, config=_autoConfig(tmp_path))
    assert pdf.exists() and not target.exists() and preview.asked == []

    confirmed = FakeDialogs()
    counts, _ = _run(cabinet, tmp_path, confirmed, config=_autoConfig(tmp_path))
    assert counts.filed == 1 and target.is_file() and confirmed.asked == []


## safety (criterion 10)


def test_previewMovesAndLearnsNothing(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    pdf = inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)
    dialogs = FakeDialogs(suggestionAsk=[FILE])

    counts, logger = _run(cabinet, tmp_path, dialogs, confirm=False)

    assert pdf.exists() and counts.filed == 1
    assert "(Preview: nothing will move" in dialogs.asked[0][1]
    assert not (tmp_path / "learned.json").exists()
    assert any(line.startswith("action: move renewal.pdf") for line in logger.lines)


def test_confirmLearnsNumbers(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)

    counts, _ = _run(cabinet, tmp_path, FakeDialogs(suggestionAsk=[FILE]))

    assert counts.learned == 1
    learned = learnedLoad(tmp_path / "learned.json").identifiers
    assert learned == {"MBNAUKM4HAP100000001": Path("Insurance/MBNA")}


def test_alreadyFiledIsTrashed(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    pdf = inboxPdf("again.pdf", AVIVA_TAX_LINES)
    copy = cabinet / "Finance/Aviva/AV1111111/old copy.pdf"
    copy.write_bytes(pdf.read_bytes())

    counts, _ = _run(cabinet, tmp_path, FakeDialogs(suggestionAsk=[FILE]))

    assert counts.duplicates == 1 and not pdf.exists()
    assert (tmp_path / "trash" / "again.pdf").is_file()


def test_differentFileWithSameNameIsNotOverwritten(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    pdf = inboxPdf("tax.pdf", AVIVA_TAX_LINES)
    taken = cabinet / "Finance/Aviva/AV1111111/2026-04-05 - Aviva, AV1111111 - Tax.pdf"
    taken.write_bytes(b"another document")
    dialogs = FakeDialogs(suggestionAsk=[FILE])

    counts, _ = _run(cabinet, tmp_path, dialogs)

    assert counts.conflicts == 1 and pdf.exists()
    assert taken.read_bytes() == b"another document"
    assert dialogs.asked[-1][:2] == ("message", "error")


def test_uppercaseExtensionAndOldestFirst(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    import os

    newer = inboxPdf("b.PDF", AVIVA_ISA_LINES)
    older = inboxPdf("a.pdf", AVIVA_TAX_LINES)
    os.utime(newer, (2_000_000_000, 2_000_000_000))
    os.utime(older, (1_000_000_000, 1_000_000_000))
    dialogs = FakeDialogs(suggestionAsk=[SKIP, SKIP])

    _run(cabinet, tmp_path, dialogs)

    texts = [entry[1] for entry in dialogs.asked]
    assert "a.pdf" in texts[0] and "b.PDF" in texts[1]
