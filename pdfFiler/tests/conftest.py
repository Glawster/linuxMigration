"""Shared fixtures for pdfFiler tests.

Golden examples reproduce only the wording that matters from three real
scans (requirement 005), with fictional names and numbers of the same shape:
  - Aviva tax letter      -> plan AV1111111
  - MBNA renewal          -> policy MBNAUKM4HAP100000001
  - Aviva ISA statement   -> account AV2222222
PDFs are real files made by ../tests/pdfFixtures.py and read by the real
pdftotext.
"""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import pytest

from pdfFixtures import pdfWrite  # repository tests/, on pythonpath

TODAY = dt.date(2026, 11, 23)

AVIVA_TAX_LINES = [
    "Any questions?",
    "Aviva",
    "PO Box 520",
    "Private and Confidential",
    "Mr A Example",
    "Your plan number",
    "AV1111111",
    "This letter shows the interest paid to you in the tax year, for the",
    "period 06 April 2025",
    "to 05 April",
    "April 2026.",
    "Interest paid on or after 6th April 2021 is paid gross. If you have to",
    "complete a tax return you",
    "Conduct Authority. Firm Reference Number 231530.",
]

MBNA_RENEWAL_LINES = [
    "A Example",
    "1 Example Road",
    "006378AECO",
    "20/10/2025",
    "MBNAUKM4HAP100000001",
    "Date:",
    "Policy",
    "Subject:",
    "MBNA Home Emergency Policy is up for renewal",
    "Policy Number:",
    "We",
    "MBNAUKM4HAP100000001",
    "Renewal",
    "Date:",
    "01/12/2025",
    "writing to let you know that your MBNA Policy is coming to an end.",
    "policy and cover will continue.",
    "of the insurance",
]

AVIVA_ISA_LINES = [
    "Any questions?",
    "Aviva",
    "PO Box 26957",
    "PDOEA02-20260524-21923-000145",
    "Statement",
    "Aviva",
    "to 22/05/2026",
    "for 23/02/2026",
    "AV2222222",
    "number:",
    "Account",
    "latest statement which shows the value of your investments on 22/05/2026",
    "online at myaviva.co.uk. You can also view any other correspondence on",
    "23/02/2028.",
    "AV2222222-001",
    "Conduct Authority. Firm Reference Number 231530.",
]


def _filed(folder: Path, *names: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        # Filed PDFs are never opened by the index, so any content will do.
        (folder / name).write_bytes(b"not a real pdf: the index reads names only")


@pytest.fixture
def cabinet(tmp_path: Path) -> Path:
    """A small cabinet shaped like the real one."""
    root = tmp_path / "myCabinets"
    (root / "Inbox").mkdir(parents=True)
    _filed(
        root / "Finance" / "Aviva" / "AV1111111",
        "2025-04-05 - Aviva, AV1111111 - Tax.pdf",
        "2025-05-14 - Aviva, AV1111111 - Statement.pdf",
        "2025-08-14 - Aviva, AV1111111 - Statement.pdf",
        "2024-01-12 - Aviva, AV1111111 - Letter From.pdf",
        "2025-08-15 - AV1111111 - Statement.pdf",
    )
    _filed(
        root / "Finance" / "Aviva" / "AV2222222",
        "2025-05-22 - Aviva, AV2222222 - Statement.pdf",
        "2025-09-01 - Aviva, AV2222222 - Statement.pdf",
        "2021-02-03 - Aviva, AV2222222 - Letter From.pdf",
    )
    _filed(root / "Finance" / "Aviva", "wilsona aviva illustration.pdf")
    _filed(
        root / "Finance" / "MBNA", *[f"2018-{month:02d}-12 - MBNA.pdf" for month in range(1, 13)]
    )
    _filed(root / "Insurance" / "MBNA", "2025-10-29 - Insurance, MBNA - Policy Documents.pdf")
    _filed(root / "Insurance", "2012-08-31 Endsleigh Student Insurance.pdf")
    _filed(
        root / "Benefits" / "Bank Statements" / "2026",
        "2026-09-30 - Direct Payments - Statement - Sep.pdf",
    )
    for person in ("Andy", "Kathy", "Adam"):
        for place in ("Family", "Pension/Old Mutual", "Health"):
            _filed(root / place / person, f"2020-01-01 - {person} - Letter From.pdf")
    _filed(root / "Archive" / "AV9999999", "2010-01-01 - Old, AV9999999 - Statement.pdf")
    return root


@pytest.fixture
def inboxPdf(cabinet: Path):
    """Write a PDF into the inbox: inboxPdf(name, lines)."""

    def write(name: str, lines: list[str]) -> Path:
        return pdfWrite(cabinet / "Inbox" / name, lines)

    return write


@pytest.fixture
def fakeBin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """gio, feh and wmctrl doubles on PATH; gio "trashes" into tmp_path/trash."""
    binDir = tmp_path / "bin"
    trash = tmp_path / "trash"
    binDir.mkdir()
    trash.mkdir()
    doubles = {
        "gio": f'#!/usr/bin/env bash\n[[ "$1" == trash ]] || exit 1\nmv -- "${{@: -1}}" "{trash}/"\n',
        "feh": "#!/usr/bin/env bash\nexit 0\n",
        "wmctrl": "#!/usr/bin/env bash\nexit 0\n",
    }
    for name, body in doubles.items():
        path = binDir / name
        path.write_text(body)
        path.chmod(0o755)
    monkeypatch.setenv("PATH", f"{binDir}:{__import__('os').environ['PATH']}")
    return binDir


pytestmark = pytest.mark.skipif(shutil.which("pdftotext") is None, reason="poppler-utils needed")
