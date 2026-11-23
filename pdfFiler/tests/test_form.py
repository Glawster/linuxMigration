"""The filing form behind the window: filling in, editing and checking."""

from __future__ import annotations

from pathlib import Path

from conftest import AVIVA_TAX_LINES, MBNA_RENEWAL_LINES, TODAY

from pdfFiler.cabinet import cabinetIndexBuild
from pdfFiler.form import formCheck, formCreate, formFolderSet, formTypeSet
from pdfFiler.learned import Learned
from pdfFiler.suggest import suggestionMake
from pdfFiler.text import textOfPdf


def _form(cabinet: Path, pdf: Path):
    index = cabinetIndexBuild(cabinet)
    text = textOfPdf(pdf)
    suggestion = suggestionMake(text, pdf.name, index, Learned(), [], TODAY)
    return formCreate(pdf, text, suggestion, index, TODAY), index


def test_formFilledFromSuggestion(cabinet, inboxPdf) -> None:
    state, _ = _form(cabinet, inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES))

    assert state.folder == "Insurance/MBNA"
    assert state.folderChoices[:2] == ["Insurance/MBNA", "Finance/MBNA"]
    assert (state.docType, state.date, state.label) == ("Renewal", "2025-10-20", "Insurance, MBNA")
    assert state.typeChoices[0] == "Renewal"


def test_checkShowsWholePathOnOneLine(cabinet, inboxPdf) -> None:
    state, _ = _form(cabinet, inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES))

    check = formCheck(state, TODAY)

    assert check.problem is None and check.outcome == "file"
    assert check.shown == "Insurance/MBNA/2025-10-20 - Insurance, MBNA - Renewal.pdf"
    assert "\n" not in check.shown
    assert (
        check.destination == cabinet / "Insurance/MBNA/2025-10-20 - Insurance, MBNA - Renewal.pdf"
    )


def test_folderChangeRecalculatesLabelTypeAndDate(cabinet, inboxPdf) -> None:
    state, index = _form(cabinet, inboxPdf("tax.pdf", AVIVA_TAX_LINES))

    formFolderSet(state, "Insurance/MBNA", index, TODAY)

    assert state.label == "Insurance, MBNA"
    assert formCheck(state, TODAY).shown.startswith("Insurance/MBNA/")
    formFolderSet(state, "Finance/Aviva/AV1111111", index, TODAY)
    assert (state.label, state.docType, state.date) == ("Aviva, AV1111111", "Tax", "2026-04-05")


def test_typedFieldsAreKept(cabinet, inboxPdf) -> None:
    state, index = _form(cabinet, inboxPdf("tax.pdf", AVIVA_TAX_LINES))
    state.label, state.date = "My label", "2026-01-02"
    state.edited |= {"label", "date"}

    formFolderSet(state, "Insurance/MBNA", index, TODAY)
    formTypeSet(state, "Statement", TODAY)

    assert (state.label, state.date) == ("My label", "2026-01-02")


def test_typeChangeRedatesUntypedDate(cabinet, inboxPdf) -> None:
    state, _ = _form(cabinet, inboxPdf("tax.pdf", AVIVA_TAX_LINES))
    assert state.date == "2026-04-05"

    formTypeSet(state, "Letter From", TODAY)

    assert state.date == "2025-04-06"  # the first written date, not the tax-year end


def test_problemsStopFiling(cabinet, inboxPdf) -> None:
    state, _ = _form(cabinet, inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES))
    cases = {
        ("folder", ""): "Choose a folder",
        ("folder", "../outside"): "inside the cabinets",
        ("date", "2026-02-30"): "YYYY-MM-DD",
        ("date", "2027-01-01"): "future",
        ("label", "  "): "label",
    }
    for (name, value), problem in cases.items():
        original = getattr(state, name)
        setattr(state, name, value)
        check = formCheck(state, TODAY)
        assert check.problem and problem in check.problem, (name, value, check.problem)
        setattr(state, name, original)


def test_conflictAndDuplicateAreShown(cabinet, inboxPdf) -> None:
    pdf = inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)
    state, _ = _form(cabinet, pdf)
    target = cabinet / "Insurance/MBNA/2025-10-20 - Insurance, MBNA - Renewal.pdf"

    target.write_bytes(b"another document")
    conflict = formCheck(state, TODAY)
    target.write_bytes(pdf.read_bytes())
    duplicate = formCheck(state, TODAY)

    assert conflict.outcome == "conflict" and "different file" in conflict.problem
    assert duplicate.outcome == "duplicate" and duplicate.problem is None


def test_keepOriginalNameUsesPdfName(cabinet, inboxPdf) -> None:
    state, _ = _form(cabinet, inboxPdf("Scan: letter.pdf", MBNA_RENEWAL_LINES))
    state.docType = "Keep Original Name"

    assert formCheck(state, TODAY).shown.endswith("- Insurance, MBNA - Scan- letter.pdf")


def test_noSuggestionStartsWithoutFolder(cabinet, inboxPdf) -> None:
    pdf = inboxPdf("scan.pdf", ["Nothing known", "Sent 14/08/2025"])
    index = cabinetIndexBuild(cabinet)

    state = formCreate(pdf, textOfPdf(pdf), None, index, TODAY)

    assert (state.folder, state.date) == ("", "2025-08-14")
    assert formCheck(state, TODAY).problem == "Choose a folder."
    formFolderSet(state, "Insurance/MBNA", index, TODAY)
    assert formCheck(state, TODAY).problem is None
