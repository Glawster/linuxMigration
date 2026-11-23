"""Date strategies (requirement 005, criteria 6 and 15-17)."""

from __future__ import annotations

import datetime as dt

import pytest
from conftest import AVIVA_ISA_LINES, AVIVA_TAX_LINES, MBNA_RENEWAL_LINES, TODAY

from pdfFiler.dates import dateChoose, dateFromFilename

D = dt.date


@pytest.mark.parametrize(
    "text, strategy, expected",
    [
        ("Danske Bank\n30 October 2026\nAccount number", "default", D(2026, 10, 30)),
        ("Printed 01/01/2025\nInvoice date: 05/03/2026", "default", D(2026, 3, 5)),
        ("Issued 1st Sept 2026", "default", D(2026, 9, 1)),
        ("Due 3 September 2026", "default", D(2026, 9, 3)),
        ("Reference 2026/11/02", "default", D(2026, 11, 2)),
        ("Date: 31/02/2026", "default", None),
        ("nothing here", "default", None),
        ("\n".join(MBNA_RENEWAL_LINES), "default", D(2025, 10, 20)),
        # criterion 6: tax documents are dated at the end of the tax year
        ("\n".join(AVIVA_TAX_LINES), "taxYearEnd", D(2026, 4, 5)),
        ("Tax year 2024/25 summary", "taxYearEnd", D(2025, 4, 5)),
        # criterion 15: period end, lines in either order
        ("\n".join(AVIVA_ISA_LINES), "statementPeriodEnd", D(2026, 5, 22)),
        ("for 23/02/2026\nto 22/05/2026", "statementPeriodEnd", D(2026, 5, 22)),
        ("to 22/05/2026\nfor 23/02/2026", "statementPeriodEnd", D(2026, 5, 22)),
        ("Period this statement relates to: 01 October 2026 to 30 October 2026",
         "statementPeriodEnd", D(2026, 10, 30)),
        ("Statement without a period, dated 14/08/2025", "statementPeriodEnd", D(2025, 8, 14)),
        ("Danske Bank\n30 October 2026\nPeriod: 01 October 2026", "standaloneLine", D(2026, 10, 30)),
    ],
)  # fmt: skip
def test_dateChoose(text: str, strategy: str, expected: dt.date | None) -> None:
    assert dateChoose(text, strategy, TODAY) == expected


def test_futureDateIsNeverUsed() -> None:
    # criterion 16: OCR's 23/02/2028 is skipped for an earlier valid date
    assert dateChoose("seen 23/02/2028.\nsent 14/08/2025", "default", TODAY) == D(2025, 8, 14)
    assert dateChoose("only 23/02/2028.", "default", TODAY) is None
    assert dateChoose("for 01/01/2026 to 23/02/2028", "statementPeriodEnd", TODAY) == D(2026, 1, 1)


def test_dateInsideReferenceIsNotRead() -> None:
    # criterion 17
    text = "PDOEA02-20260524-21923-000145\nref 2026-05-24-AB\nX20260524"
    assert dateChoose(text, "default", TODAY) is None


def test_unknownStrategyIsRefused() -> None:
    with pytest.raises(ValueError):
        dateChoose("", "lunar", TODAY)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("scan_20261102.pdf", D(2026, 11, 2)),
        ("letter 2026_10_30.pdf", D(2026, 10, 30)),
        ("receipt 05.03.2026.pdf", D(2026, 3, 5)),
        ("bad 2026-02-30.pdf", None),
        ("future 2027-01-01.pdf", None),
        ("no date.pdf", None),
    ],
)
def test_dateFromFilename(name: str, expected: dt.date | None) -> None:
    assert dateFromFilename(name, TODAY) == expected
