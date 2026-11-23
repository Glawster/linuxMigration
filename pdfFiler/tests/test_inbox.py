"""The `inbox file` workflow (criteria 7-10 and the 1.4a6 safety rules).

The filing window is a scripted stand-in that edits the real form and
returns decisions; text, suggestions, form checks, filing, learning and the
gio double are real.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from conftest import AVIVA_ISA_LINES, AVIVA_TAX_LINES, MBNA_RENEWAL_LINES, TODAY

from pdfFiler.form import FILE, SKIP, STOP, Decision, formCheck, formFolderSet
from pdfFiler.inbox import Options, inboxFile, inboxIndex
from pdfFiler.learned import learnedLoad

EXAMPLE_CONFIG = Path(__file__).resolve().parents[1] / "config.example.json"


class FakeWindow:
    """Plays a script of steps: FILE, SKIP, STOP, or a function that edits
    the form first and returns one of those."""

    def __init__(self, index, *steps) -> None:
        self.index = index
        self.steps = list(steps)
        self.shown: list = []
        self.messages: list[tuple[str, str]] = []

    def decide(self, state, position: int, total: int) -> Decision:
        self.shown.append((state.pdf.name, position, total, formCheck(state, TODAY).shown))
        step = self.steps.pop(0) if self.steps else SKIP
        action = step(state, self.index) if callable(step) else step
        return Decision(action, formCheck(state, TODAY) if action == FILE else None)

    def message(self, kind: str, text: str) -> None:
        self.messages.append((kind, text))


class FakeLogger:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def value(self, name, value):
        self.lines.append(f"value: {name}: {value}")

    def __getattr__(self, level):
        def log(message, *args):
            self.lines.append(f"{level}: {message % args if args else message}")

        return log


def _options(cabinet: Path, tmp_path: Path, confirm: bool = True, config=None) -> Options:
    return Options(
        root=cabinet,
        inbox=cabinet / "Inbox",
        dryRun=not confirm,
        configPath=config or tmp_path / "no-config.json",
        learnedPath=tmp_path / "learned.json",
        today=TODAY,
    )


def _run(cabinet, tmp_path, *steps, confirm=True, config=None):
    options = _options(cabinet, tmp_path, confirm, config)
    index = inboxIndex(options)
    window = FakeWindow(index, *steps)
    logger = FakeLogger()
    counts = inboxFile(options, logger, window, index)
    return counts, window, logger


## window decisions


def test_fileAcceptsSuggestion(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    # criterion 7: one window, File files it as shown
    pdf = inboxPdf("2026-11-23.pdf", AVIVA_TAX_LINES)

    counts, window, _ = _run(cabinet, tmp_path, FILE)

    filed = cabinet / "Finance/Aviva/AV1111111/2026-04-05 - Aviva, AV1111111 - Tax.pdf"
    assert counts.filed == 1 and filed.is_file() and not pdf.exists()
    assert window.shown == [
        ("2026-11-23.pdf", 1, 1, "Finance/Aviva/AV1111111/2026-04-05 - Aviva, AV1111111 - Tax.pdf")
    ]


def test_changedFolderFilesThere(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)

    def toFinance(state, index):
        formFolderSet(state, "Finance/MBNA", index, TODAY)
        return FILE

    _run(cabinet, tmp_path, toFinance)

    assert (cabinet / "Finance/MBNA/2025-10-20 - MBNA - Renewal.pdf").is_file()


def test_skipLeavesPdfAndMovesOn(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    first = inboxPdf("a.pdf", AVIVA_TAX_LINES)
    second = inboxPdf("b.pdf", AVIVA_ISA_LINES)

    counts, window, _ = _run(cabinet, tmp_path, SKIP, SKIP)

    assert counts.skipped == 2 and first.exists() and second.exists()
    assert [entry[1:3] for entry in window.shown] == [(1, 2), (2, 2)]


def test_stopEndsTheRun(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    inboxPdf("a.pdf", ["nothing"])
    inboxPdf("b.pdf", ["nothing"])

    counts, window, logger = _run(cabinet, tmp_path, STOP)

    assert counts.cancelled and len(window.shown) == 1
    assert "info: stopped by user" in logger.lines


def test_noSuggestionStillUsesTheWindow(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    # criterion 9 (revised): the same window, with no folder until chosen
    (cabinet / "Taxes").mkdir()
    inboxPdf("scan.pdf", ["A letter with nothing to go on", "Sent 01/02/2026"])

    def choose(state, index):
        assert state.folder == ""
        formFolderSet(state, "Taxes", index, TODAY)
        state.docType = "Invoice"
        return FILE

    _run(cabinet, tmp_path, choose)

    assert (cabinet / "Taxes/2026-02-01 - Taxes - Invoice.pdf").is_file()


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


def test_autoRuleFilesWithoutWindowOnlyWithConfirm(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    # criterion 8
    pdf = inboxPdf("Statement 950246 60153699.PDF", _DP_LINES)
    target = (
        cabinet / "Benefits/Bank Statements/2026/2026-10-30 - Direct Payments - Statement - Oct.pdf"
    )

    _, preview, _ = _run(cabinet, tmp_path, confirm=False, config=_autoConfig(tmp_path))
    assert pdf.exists() and not target.exists() and preview.shown == []

    counts, confirmed, _ = _run(cabinet, tmp_path, config=_autoConfig(tmp_path))
    assert counts.filed == 1 and target.is_file() and confirmed.shown == []


## safety (criterion 10)


def test_previewMovesAndLearnsNothing(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    pdf = inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)

    counts, _, logger = _run(cabinet, tmp_path, FILE, confirm=False)

    assert pdf.exists() and counts.filed == 1
    assert not (tmp_path / "learned.json").exists()
    assert any(line.startswith("action: move renewal.pdf") for line in logger.lines)


def test_confirmLearnsNumbers(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)

    counts, _, _ = _run(cabinet, tmp_path, FILE)

    assert counts.learned == 1
    learned = learnedLoad(tmp_path / "learned.json").identifiers
    assert learned == {"MBNAUKM4HAP100000001": Path("Insurance/MBNA")}


def test_alreadyFiledIsTrashed(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    pdf = inboxPdf("again.pdf", AVIVA_TAX_LINES)
    (cabinet / "Finance/Aviva/AV1111111/old copy.pdf").write_bytes(pdf.read_bytes())

    counts, _, _ = _run(cabinet, tmp_path, FILE)

    assert counts.duplicates == 1 and not pdf.exists()
    assert (tmp_path / "trash" / "again.pdf").is_file()


def test_nameTakenAfterTheWindowIsNotOverwritten(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    # The window checks too, but a file can appear between check and move.
    pdf = inboxPdf("tax.pdf", AVIVA_TAX_LINES)
    taken = cabinet / "Finance/Aviva/AV1111111/2026-04-05 - Aviva, AV1111111 - Tax.pdf"

    def appear(state, index):
        taken.write_bytes(b"another document")
        return FILE

    options = _options(cabinet, tmp_path)
    index = inboxIndex(options)

    class LateWindow(FakeWindow):
        def decide(self, state, position, total):
            decision = Decision(FILE, formCheck(state, TODAY))
            appear(state, index)
            return decision

    window = LateWindow(index)
    counts = inboxFile(options, FakeLogger(), window, index)

    assert counts.conflicts == 1 and pdf.exists()
    assert taken.read_bytes() == b"another document"
    assert window.messages[0][0] == "error"


def test_uppercaseExtensionAndOldestFirst(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    newer = inboxPdf("b.PDF", AVIVA_ISA_LINES)
    older = inboxPdf("a.pdf", AVIVA_TAX_LINES)
    os.utime(newer, (2_000_000_000, 2_000_000_000))
    os.utime(older, (1_000_000_000, 1_000_000_000))

    _, window, _ = _run(cabinet, tmp_path, SKIP, SKIP)

    assert [entry[0] for entry in window.shown] == ["a.pdf", "b.PDF"]
