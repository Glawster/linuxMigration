"""The real filing window (tkinter), driven by scheduled key presses and
button clicks. Skipped when there is no display."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from conftest import MBNA_RENEWAL_LINES, TODAY

from pdfFiler.cabinet import cabinetIndexBuild
from pdfFiler.form import FILE, SKIP, STOP, formCreate
from pdfFiler.learned import Learned
from pdfFiler.suggest import suggestionMake
from pdfFiler.text import textOfPdf

pytestmark = pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="needs a display")


@pytest.fixture
def window(cabinet: Path):
    from pdfFiler.ui.filingWindow import FilingWindow

    filingWindow = FilingWindow(cabinetIndexBuild(cabinet), TODAY, dryRun=True)
    filingWindow.root.withdraw()
    # Watchdog: a test that never clicks ends instead of hanging, and fails.
    fired = []

    def watchdog() -> None:
        fired.append(True)
        filingWindow._decide(STOP)

    filingWindow.root.after(10_000, watchdog)
    yield filingWindow
    filingWindow.close()
    assert not fired, "the window was left waiting; the watchdog closed it"


def _state(cabinet: Path, pdf: Path):
    index = cabinetIndexBuild(cabinet)
    text = textOfPdf(pdf)
    return formCreate(
        pdf, text, suggestionMake(text, pdf.name, index, Learned(), [], TODAY), index, TODAY
    )


def _then(window, *actions, delay: int = 300) -> None:
    """Run actions one after another once the window is showing."""
    for number, action in enumerate(actions, start=1):
        window.root.after(delay * number, action)


def test_showsSuggestionOnOneLineAndFiles(window, cabinet, inboxPdf) -> None:
    state = _state(cabinet, inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES))
    seen = {}

    def look():
        seen["fileAs"] = window.fileAsVar.get()
        seen["folder"] = window.folderBox.get()
        seen["choices"] = list(window.folderBox.cget("values"))
        seen["banner"] = True
        window.fileButton.invoke()

    _then(window, look)
    decision = window.decide(state, 1, 3)

    assert seen["fileAs"] == "Insurance/MBNA/2025-10-20 - Insurance, MBNA - Renewal.pdf"
    assert seen["folder"] == "Insurance/MBNA"
    assert seen["choices"][:2] == ["Insurance/MBNA", "Finance/MBNA"]
    assert decision.action == FILE
    assert decision.check.destination == (
        cabinet / "Insurance/MBNA/2025-10-20 - Insurance, MBNA - Renewal.pdf"
    )
    assert window.root.title() == "pdfFiler - renewal.pdf (1 of 3)"


def test_choosingAnotherFolderUpdatesTheName(window, cabinet, inboxPdf) -> None:
    state = _state(cabinet, inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES))
    seen = {}

    def choose():
        window.folderBox.set("Finance/MBNA")
        window.folderBox.event_generate("<<ComboboxSelected>>")

    def look():
        seen["fileAs"] = window.fileAsVar.get()
        seen["label"] = window.labelEntry.get()
        window.fileButton.invoke()

    _then(window, choose, look)
    decision = window.decide(state, 1, 1)

    assert seen == {"fileAs": "Finance/MBNA/2025-10-20 - MBNA - Renewal.pdf", "label": "MBNA"}
    assert decision.check.destination.parent == cabinet / "Finance/MBNA"


def test_badDateDisablesFileAndEnter(window, cabinet, inboxPdf) -> None:
    state = _state(cabinet, inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES))
    seen = {}

    def typeBadDate():
        window.dateEntry.delete(0, "end")
        window.dateEntry.insert(0, "2027-01-01")
        window._typed("date", window.dateEntry)  # what the KeyRelease binding runs

    def look():
        seen["button"] = str(window.fileButton.cget("state"))
        seen["status"] = window.statusLabel.cget("text")
        window._fileIfReady()  # what Enter runs: nothing while the form is wrong
        seen["stillOpen"] = window._decision is None
        window._decide(SKIP)  # what Esc runs

    _then(window, typeBadDate, look)
    decision = window.decide(state, 1, 1)

    assert seen["button"] == "disabled" and "future" in seen["status"]
    assert seen["stillOpen"] and decision.action == SKIP
    assert state.date == "2027-01-01" and "date" in state.edited


def test_keysAreBound(window) -> None:
    for sequence in ("<Return>", "<KP_Enter>", "<Escape>"):
        assert window.root.bind(sequence), sequence


def test_duplicateOffersTrash(window, cabinet, inboxPdf) -> None:
    pdf = inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)
    (cabinet / "Insurance/MBNA/copy.pdf").write_bytes(pdf.read_bytes())
    seen = {}

    def look():
        seen["button"] = window.fileButton.cget("text")
        seen["status"] = window.statusLabel.cget("text")
        window._decide(STOP)

    _then(window, look)
    decision = window.decide(_state(cabinet, pdf), 1, 1)

    assert seen["button"] == "Trash duplicate" and "copy.pdf" in seen["status"]
    assert decision.action == STOP


def test_closingTheWindowStops(window, cabinet, inboxPdf) -> None:
    state = _state(cabinet, inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES))
    # Run the window manager's close command, as clicking the X would.
    _then(window, lambda: window.root.tk.call(window.root.protocol("WM_DELETE_WINDOW")))

    assert window.decide(state, 1, 1).action == STOP
