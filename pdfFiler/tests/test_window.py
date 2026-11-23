"""The real Qt filing window, driven by timers that change fields and press
buttons. Runs off-screen (QT_QPA_PLATFORM=offscreen), so no window appears
and no display is needed."""

from __future__ import annotations

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from conftest import MBNA_RENEWAL_LINES, TODAY  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QCloseEvent  # noqa: E402

from pdfFiler.cabinet import cabinetIndexBuild  # noqa: E402
from pdfFiler.form import FILE, SKIP, STOP, formCreate  # noqa: E402
from pdfFiler.learned import Learned  # noqa: E402
from pdfFiler.suggest import suggestionMake  # noqa: E402
from pdfFiler.text import textOfPdf  # noqa: E402
from pdfFiler.ui.filingWindow import FilingWindow  # noqa: E402


@pytest.fixture
def window(cabinet: Path):
    filingWindow = FilingWindow(cabinetIndexBuild(cabinet), TODAY, dryRun=True)
    # Watchdog: a test that never presses a button ends instead of hanging,
    # and fails.
    fired = []

    def watchdog() -> None:
        fired.append(True)
        filingWindow._decide(STOP)

    timer = QTimer(singleShot=True, interval=10_000, timeout=watchdog)
    timer.start()
    yield filingWindow
    timer.stop()
    filingWindow.close()
    assert not fired, "the window was left waiting; the watchdog closed it"


def _state(cabinet: Path, pdf: Path):
    index = cabinetIndexBuild(cabinet)
    text = textOfPdf(pdf)
    suggestion = suggestionMake(text, pdf.name, index, Learned(), [], TODAY)
    return formCreate(pdf, text, suggestion, index, TODAY)


def _then(*actions, delay: int = 100) -> None:
    """Run actions one after another once the window is waiting."""
    for number, action in enumerate(actions, start=1):
        QTimer.singleShot(delay * number, action)


def test_showsSuggestionOnOneLineAndFiles(window, cabinet, inboxPdf) -> None:
    state = _state(cabinet, inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES))
    seen = {}

    def look():
        seen["fileAs"] = window.fileAsEdit.text()
        seen["folder"] = window.folderBox.currentText()
        seen["choices"] = [window.folderBox.itemText(i) for i in range(window.folderBox.count())]
        seen["pages"] = window.pageView.document.pageCount()
        window.fileButton.click()

    _then(look)
    decision = window.decide(state, 1, 3)

    assert seen["fileAs"] == "Insurance/MBNA/2025-10-20 - Insurance, MBNA - Renewal.pdf"
    assert seen["folder"] == "Insurance/MBNA"
    assert seen["choices"][:2] == ["Insurance/MBNA", "Finance/MBNA"]
    assert seen["pages"] == 1
    assert decision.action == FILE
    assert decision.check.destination == (
        cabinet / "Insurance/MBNA/2025-10-20 - Insurance, MBNA - Renewal.pdf"
    )
    assert window.windowTitle() == "pdfFiler - renewal.pdf (1 of 3)"


def test_choosingAnotherFolderUpdatesTheName(window, cabinet, inboxPdf) -> None:
    state = _state(cabinet, inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES))
    seen = {}

    def choose():
        window.folderBox.setCurrentIndex(1)  # Finance/MBNA
        window.folderBox.activated.emit(1)  # as when the user picks it

    def look():
        seen["fileAs"] = window.fileAsEdit.text()
        seen["label"] = window.labelEdit.text()
        window.fileButton.click()

    _then(choose, look)
    decision = window.decide(state, 1, 1)

    assert seen == {"fileAs": "Finance/MBNA/2025-10-20 - MBNA - Renewal.pdf", "label": "MBNA"}
    assert decision.check.destination.parent == cabinet / "Finance/MBNA"


def test_badDateDisablesFile(window, cabinet, inboxPdf) -> None:
    state = _state(cabinet, inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES))
    seen = {}

    def typeBadDate():
        window.dateEdit.setText("2027-01-01")
        window.dateEdit.textEdited.emit("2027-01-01")  # as when the user types

    def look():
        seen["enabled"] = window.fileButton.isEnabled()
        seen["status"] = window.statusLabel.text()
        window._fileIfReady()  # what Enter runs: nothing while the form is wrong
        seen["stillOpen"] = window._decision is None
        window.skipButton.click()

    _then(typeBadDate, look)
    decision = window.decide(state, 1, 1)

    assert not seen["enabled"] and "future" in seen["status"]
    assert seen["stillOpen"] and decision.action == SKIP
    assert state.date == "2027-01-01" and "date" in state.edited


def test_duplicateOffersTrash(window, cabinet, inboxPdf) -> None:
    pdf = inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)
    (cabinet / "Insurance/MBNA/copy.pdf").write_bytes(pdf.read_bytes())
    seen = {}

    def look():
        seen["button"] = window.fileButton.text()
        seen["status"] = window.statusLabel.text()
        window.stopButton.click()

    _then(look)
    decision = window.decide(_state(cabinet, pdf), 1, 1)

    assert seen["button"] == "Trash duplicate" and "copy.pdf" in seen["status"]
    assert decision.action == STOP


def test_closingTheWindowStops(window, cabinet, inboxPdf) -> None:
    state = _state(cabinet, inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES))
    _then(lambda: window.closeEvent(QCloseEvent()))

    assert window.decide(state, 1, 1).action == STOP


def test_shortcutsAreEnterAndEscape(window) -> None:
    from PySide6.QtGui import QShortcut

    keys = {shortcut.key().toString() for shortcut in window.findChildren(QShortcut)}
    assert {"Return", "Enter", "Esc"} <= keys
