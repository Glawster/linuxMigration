"""Suggestions: golden examples and criteria 1-6, 13 and 14.

Each golden test writes a real PDF and reads it with the real pdftotext,
then runs the real index, rules, learning and suggestion code.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import AVIVA_ISA_LINES, AVIVA_TAX_LINES, MBNA_RENEWAL_LINES, TODAY

from pdfFiler.cabinet import cabinetIndexBuild
from pdfFiler.learned import Learned, learnedLoad, learnedNumbersFind, learnedRecord
from pdfFiler.naming import fileNameBuild, typeChoose, typesOffered
from pdfFiler.rules import rulesLoad
from pdfFiler.suggest import suggestionMake
from pdfFiler.text import textOfPdf

EXAMPLE_CONFIG = Path(__file__).resolve().parents[1] / "config.example.json"


def _suggest(cabinet: Path, pdf: Path, learned: Learned | None = None, rules=None):
    return suggestionMake(
        textOfPdf(pdf),
        pdf.name,
        cabinetIndexBuild(cabinet),
        learned or Learned(),
        rules or [],
        TODAY,
    )


## golden examples


def test_goldenAvivaTaxLetter(cabinet: Path, inboxPdf) -> None:
    # criteria 1, 4, 5 and 6
    suggestion = _suggest(cabinet, inboxPdf("2026-11-23.pdf", AVIVA_TAX_LINES))

    assert f"{suggestion.folder}/{suggestion.fileName()}" == (
        "Finance/Aviva/AV1111111/2026-04-05 - Aviva, AV1111111 - Tax.pdf"
    )
    assert "matched AV1111111" in suggestion.reasons


def test_goldenMbnaRenewal(cabinet: Path, inboxPdf) -> None:
    # criteria 2, 5 and 13
    suggestion = _suggest(cabinet, inboxPdf("2026-11-23 2.pdf", MBNA_RENEWAL_LINES))

    assert f"{suggestion.folder}/{suggestion.fileName()}" == (
        "Insurance/MBNA/2025-10-20 - Insurance, MBNA - Renewal.pdf"
    )
    assert Path("Finance/MBNA") == suggestion.runnerUps[0].folder
    assert "insurance" in suggestion.reasonText()


def test_goldenAvivaIsaStatement(cabinet: Path, inboxPdf) -> None:
    # criteria 1, 15, 16 and 17
    suggestion = _suggest(cabinet, inboxPdf("2026-11-23 3.pdf", AVIVA_ISA_LINES))

    assert f"{suggestion.folder}/{suggestion.fileName()}" == (
        "Finance/Aviva/AV2222222/2026-05-22 - Aviva, AV2222222 - Statement.pdf"
    )


def test_goldenDirectPaymentsRuleMatchesFileDpStatements(cabinet: Path, inboxPdf) -> None:
    # criterion 3, and ADR 011: the rule names the file as fileDpStatements does
    pdf = inboxPdf(
        "Statement 950246 60153699.PDF",
        [
            "Danske Bank",
            "Website: www.danskebank.co.uk",
            "30 October 2026",
            "Account number: 950246 60153699",
            "Period this statement relates to: 01 October 2026 to 30 October 2026",
            "Aviva",
        ],
    )

    suggestion = _suggest(cabinet, pdf, rules=rulesLoad(EXAMPLE_CONFIG))

    assert f"{suggestion.folder}/{suggestion.fileName()}" == (
        "Benefits/Bank Statements/2026/2026-10-30 - Direct Payments - Statement - Oct.pdf"
    )
    assert suggestion.reasons == ["rule: Direct Payments bank statement"]


## learning


def test_learnedNumberFindsFolderNextTime(cabinet: Path, inboxPdf, tmp_path: Path) -> None:
    # criterion 14: file the renewal, then next year's letter matches by number
    learnedPath = tmp_path / "learned.json"
    first = inboxPdf("first.pdf", MBNA_RENEWAL_LINES)
    learnedRecord(learnedPath, learnedNumbersFind(textOfPdf(first)), Path("Insurance/MBNA"))
    nextYear = inboxPdf(
        "next.pdf", ["Dear customer", "Ref MBNAUKM4HAP100000001", "Letter 14/10/2026"]
    )

    suggestion = _suggest(cabinet, nextYear, learned=learnedLoad(learnedPath))

    assert suggestion.folder == Path("Insurance/MBNA")
    assert "matched learned number MBNAUKM4HAP100000001" in suggestion.reasons


## evidence


def test_identifierOutranksFolderName(cabinet: Path, inboxPdf) -> None:
    # criterion 2: a folder-name word ranks below an identifier
    suggestion = _suggest(cabinet, inboxPdf("x.pdf", ["MBNA and Aviva", "AV2222222", "01/02/2026"]))
    assert suggestion.folder == Path("Finance/Aviva/AV2222222")


def test_ambiguousPersonFolderIsNotEvidence(cabinet: Path, inboxPdf) -> None:
    # "Andy" names nine folders here, so a letter to Andy suggests nothing
    assert _suggest(cabinet, inboxPdf("x.pdf", ["Dear Andy", "01/02/2026"])) is None


def test_ordinaryWordsDoNotMatchFolders(cabinet: Path, inboxPdf) -> None:
    (cabinet / "Work" / "basic").mkdir(parents=True)
    (cabinet / "Work" / "Basic").mkdir(parents=True)
    assert _suggest(cabinet, inboxPdf("x.pdf", ["a basic summary", "01/02/2026"])) is None


## naming


def test_typeChoose(cabinet: Path) -> None:
    index = cabinetIndexBuild(cabinet)
    policyFolder = index.folder(Path("Insurance/MBNA"))
    planFolder = index.folder(Path("Finance/Aviva/AV1111111"))

    assert typeChoose("Your policy is up for renewal", policyFolder, index)[0] == "Renewal"
    assert typeChoose("tax year summary, tax deducted", planFolder, index)[0] == "Tax"
    assert typeChoose("Dear customer", planFolder, index)[0] == "Statement"
    assert typeChoose("Dear customer", index.folder(Path("Nowhere")), index)[0] == "Other"


def test_typesOfferedPutsSuggestionFirst(cabinet: Path) -> None:
    info = cabinetIndexBuild(cabinet).folder(Path("Insurance/MBNA"))
    offered = typesOffered("Renewal", info)
    assert offered[:2] == ["Renewal", "Policy Documents"]
    assert len(offered) == len(set(offered))


@pytest.mark.parametrize(
    "template, expected",
    [
        ("{date} - {label} - {type}.pdf", "2026-10-30 - Aviva, AV1 - Tax.pdf"),
        ("{date} - {label} - {type} - {Mon}.pdf", "2026-10-30 - Aviva, AV1 - Tax - Oct.pdf"),
        ("{year}/{date}.pdf", "2026-2026-10-30.pdf"),
    ],
)
def test_fileNameBuild(template: str, expected: str) -> None:
    import datetime as dt

    assert fileNameBuild(template, dt.date(2026, 10, 30), "Aviva, AV1", "Tax") == expected
