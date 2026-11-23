"""
tests/test_pdfFiler.py

Tests for pdfFiler.sh.

The filing tests run the real script with the real pdftotext, pdftoppm,
date, cmp and mv on generated PDFs in temporary folders. zenity, feh, wmctrl
and gio are command doubles: zenity answers from environment variables and
records each dialog, and gio "trashes" into a temporary folder. The date
tests source the script and call its date functions directly.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdfFixtures import pdfWrite  # noqa: E402

organiseMyProjects = pytest.importorskip("organiseMyProjects")

SCRIPT = Path(__file__).resolve().parent.parent / "pdfFiler.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("pdftotext") is None or shutil.which("pdftoppm") is None,
    reason="poppler-utils is required",
)

_ZENITY = r"""#!/usr/bin/env bash
# zenity double: answers from PDF_ZENITY_* and logs each dialog kind.
echo "$1" >>"$PDF_ZENITY_LOG"
case "$1" in
    --file-selection) [[ "$PDF_ZENITY_FOLDER" == CANCEL ]] && exit 1; echo "$PDF_ZENITY_FOLDER" ;;
    --list) [[ "$PDF_ZENITY_TYPE" == CANCEL ]] && exit 1; echo "$PDF_ZENITY_TYPE" ;;
    --entry) [[ -z "${PDF_ZENITY_DATE:-}" ]] && exit 1; echo "$PDF_ZENITY_DATE" ;;
    --question) exit "${PDF_ZENITY_QUESTION:-0}" ;;
    *) exit 0 ;;
esac
"""


## helpers


def _doubleWrite(fakeBin: Path, name: str, body: str) -> None:
    path = fakeBin / name
    path.write_text(body)
    path.chmod(0o755)


def _run(
    root: Path, *args: str, **answers: str
) -> tuple[subprocess.CompletedProcess, list[str]]:
    """Run pdfFiler.sh against root with scripted dialog answers.

    Returns the process result and the list of dialogs shown.
    """
    work = root.parent
    fakeBin = work / "bin"
    trash = work / "trash"
    fakeBin.mkdir(exist_ok=True)
    trash.mkdir(exist_ok=True)
    dialogLog = work / "dialogs.log"
    dialogLog.write_text("")
    _doubleWrite(fakeBin, "zenity", _ZENITY)
    _doubleWrite(fakeBin, "feh", "#!/usr/bin/env bash\nexit 0\n")
    _doubleWrite(fakeBin, "wmctrl", "#!/usr/bin/env bash\nexit 0\n")
    _doubleWrite(
        fakeBin,
        "gio",
        f'#!/usr/bin/env bash\n[[ "$1" == trash ]] || exit 1\nmv -- "${{@: -1}}" "{trash}/"\n',
    )

    env = dict(os.environ)
    env.update(
        PATH=f"{fakeBin}{os.pathsep}{env['PATH']}",
        LOG_UTILS=str(Path(organiseMyProjects.__file__).parent / "logUtils.sh"),
        XDG_STATE_HOME=str(work / "state"),
        HOME=str(work / "home"),
        PDF_ZENITY_LOG=str(dialogLog),
        PDF_ZENITY_FOLDER=answers.get("folder", ""),
        PDF_ZENITY_TYPE=answers.get("docType", "Invoice"),
        PDF_ZENITY_DATE=answers.get("date", ""),
        PDF_ZENITY_QUESTION=answers.get("question", "0"),
    )
    result = subprocess.run(
        [str(SCRIPT), "--root", str(root), *args],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return result, dialogLog.read_text().split()


def _dateCall(function: str, value: str) -> str:
    """Source the script and print what a date function returns."""
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source "$1"; {function} "$2" || echo FAIL',
            "bash",
            str(SCRIPT),
            value,
        ],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


@pytest.fixture
def cabinets(tmp_path: Path) -> Path:
    root = tmp_path / "myCabinets"
    (root / "Inbox").mkdir(parents=True)
    (root / "Taxes").mkdir()
    (tmp_path / "home").mkdir()
    return root


## date


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Danske Bank\n30 October 2026\nAccount number: 1", "2026-10-30"),
        ("Printed 01/01/2025\nInvoice date: 05/03/2026", "2026-03-05"),
        ("Issued 1st Sept 2026", "2026-09-01"),
        ("Due 3 September 2026", "2026-09-03"),
        ("Reference 2026/11/02", "2026-11-02"),
        ("Paid 30/10/2026", "2026-10-30"),
        ("Date: 31/02/2026", "FAIL"),
        ("31 February 2026", "FAIL"),
        ("no date here", "FAIL"),
    ],
)
def test_dateFromText(text: str, expected: str) -> None:
    assert _dateCall("dateFromText", text) == expected


@pytest.mark.parametrize(
    "name, expected",
    [
        ("scan_20261102.pdf", "2026-11-02"),
        ("letter 2026_10_30.pdf", "2026-10-30"),
        ("receipt 05.03.2026.pdf", "2026-03-05"),
        ("bad 2026-02-30.pdf", "FAIL"),
        ("no date.pdf", "FAIL"),
    ],
)
def test_dateFromFilename(name: str, expected: str) -> None:
    assert _dateCall("dateFromFilename", name) == expected


## filing


def test_previewMovesNothing(cabinets: Path) -> None:
    # Arrange
    pdf = pdfWrite(cabinets / "Inbox" / "scan.pdf", ["HMRC", "Date: 30/10/2026"])

    # Act
    result, dialogs = _run(cabinets, folder=str(cabinets / "Taxes"))

    # Assert
    assert result.returncode == 0, result.stderr
    assert pdf.exists()
    assert list((cabinets / "Taxes").iterdir()) == []
    assert "2026-10-30 - Taxes - Invoice.pdf" in result.stdout
    assert "--question" in dialogs


def test_confirmFilesWithDateFromPdf(cabinets: Path) -> None:
    # Arrange
    pdf = pdfWrite(cabinets / "Inbox" / "scan.pdf", ["Invoice", "30 October 2026"])
    content = pdf.read_bytes()

    # Act
    result, _ = _run(cabinets, "--confirm", folder=str(cabinets / "Taxes"))

    # Assert
    filed = cabinets / "Taxes" / "2026-10-30 - Taxes - Invoice.pdf"
    assert result.returncode == 0, result.stderr
    assert not pdf.exists()
    assert filed.read_bytes() == content


def test_uppercaseExtensionIsFiled(cabinets: Path) -> None:
    # Arrange
    pdfWrite(cabinets / "Inbox" / "Statement 1.PDF", ["30 October 2026"])

    # Act
    result, _ = _run(
        cabinets, "-y", folder=str(cabinets / "Taxes"), docType="Statement"
    )

    # Assert
    assert result.returncode == 0, result.stderr
    assert (cabinets / "Taxes" / "2026-10-30 - Taxes - Statement.pdf").is_file()


def test_yearFolderUsesParentName(cabinets: Path) -> None:
    # Arrange
    yearDir = cabinets / "Bank Statements" / "2026"
    yearDir.mkdir(parents=True)
    pdfWrite(cabinets / "Inbox" / "download.pdf", ["30 October 2026"])

    # Act
    result, _ = _run(cabinets, "-y", folder=str(yearDir), docType="Statement")

    # Assert
    assert result.returncode == 0, result.stderr
    assert (yearDir / "2026-10-30 - Bank Statements - Statement.pdf").is_file()


def test_dateFallsBackToFilenameThenPrompt(cabinets: Path) -> None:
    # Arrange: no date in either PDF; one has a dated name.
    named = pdfWrite(cabinets / "Inbox" / "scan_20260115.pdf", ["no date"])
    os.utime(named, (1, 1))
    pdfWrite(cabinets / "Inbox" / "scan.pdf", ["still no date"])

    # Act
    result, dialogs = _run(
        cabinets, "-y", folder=str(cabinets / "Taxes"), date="2026-02-01"
    )

    # Assert
    taxes = sorted(path.name for path in (cabinets / "Taxes").iterdir())
    assert result.returncode == 0, result.stderr
    assert taxes == [
        "2026-01-15 - Taxes - Invoice.pdf",
        "2026-02-01 - Taxes - Invoice.pdf",
    ]
    assert dialogs.count("--entry") == 1


def test_differentFileWithSameNameIsNotOverwritten(cabinets: Path) -> None:
    # Arrange
    pdf = pdfWrite(cabinets / "Inbox" / "scan.pdf", ["30 October 2026"])
    existing = cabinets / "Taxes" / "2026-10-30 - Taxes - Invoice.pdf"
    existing.write_bytes(b"another document")

    # Act
    result, dialogs = _run(cabinets, "--confirm", folder=str(cabinets / "Taxes"))

    # Assert
    assert result.returncode == 0, result.stderr
    assert pdf.exists()
    assert existing.read_bytes() == b"another document"
    assert "--error" in dialogs


def test_alreadyFiledIsTrashed(cabinets: Path) -> None:
    # Arrange
    pdf = pdfWrite(cabinets / "Inbox" / "scan.pdf", ["30 October 2026"])
    shutil.copy(pdf, cabinets / "Taxes" / "old name.pdf")

    # Act
    result, _ = _run(cabinets, "--confirm", folder=str(cabinets / "Taxes"))

    # Assert
    assert result.returncode == 0, result.stderr
    assert not pdf.exists()
    assert (cabinets.parent / "trash" / "scan.pdf").is_file()
    assert [path.name for path in (cabinets / "Taxes").iterdir()] == ["old name.pdf"]


def test_decliningMovesOnWithoutLooping(cabinets: Path) -> None:
    # Arrange
    first = pdfWrite(cabinets / "Inbox" / "a.pdf", ["30 October 2026"])
    second = pdfWrite(cabinets / "Inbox" / "b.pdf", ["31 October 2026"])

    # Act
    result, dialogs = _run(
        cabinets, "--confirm", folder=str(cabinets / "Taxes"), question="1"
    )

    # Assert
    assert result.returncode == 0, result.stderr
    assert first.exists() and second.exists()
    assert dialogs.count("--question") == 2


def test_folderOutsideCabinetsIsRefused(cabinets: Path, tmp_path: Path) -> None:
    # Arrange
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    pdf = pdfWrite(cabinets / "Inbox" / "scan.pdf", ["30 October 2026"])

    # Act
    result, dialogs = _run(cabinets, "--confirm", folder=str(outside))

    # Assert
    assert result.returncode == 0, result.stderr
    assert pdf.exists()
    assert list(outside.iterdir()) == []
    assert "--error" in dialogs


def test_cancellingFolderStopsRun(cabinets: Path) -> None:
    # Arrange
    pdfWrite(cabinets / "Inbox" / "a.pdf", ["30 October 2026"])
    pdfWrite(cabinets / "Inbox" / "b.pdf", ["30 October 2026"])

    # Act
    result, dialogs = _run(cabinets, "--confirm", folder="CANCEL")

    # Assert
    assert result.returncode == 0, result.stderr
    assert dialogs.count("--file-selection") == 1
    assert "cancelled by user" in result.stdout


## environment


def test_systemTmpdirIsLeftAlone(cabinets: Path, tmp_path: Path) -> None:
    # Arrange: the old script deleted whatever TMPDIR pointed at.
    systemTmp = tmp_path / "systemTmp"
    systemTmp.mkdir()
    sentinel = systemTmp / "keep.txt"
    sentinel.write_text("keep")
    os.environ["TMPDIR"] = str(systemTmp)
    try:
        # Act
        result, _ = _run(cabinets, "--confirm")
    finally:
        del os.environ["TMPDIR"]

    # Assert
    assert result.returncode == 0, result.stderr
    assert sentinel.read_text() == "keep"


def test_missingCabinetsFailsFast(tmp_path: Path) -> None:
    # Arrange
    (tmp_path / "home").mkdir()

    # Act
    result, _ = _run(tmp_path / "missing")

    # Assert
    assert result.returncode == 1
    assert "Cabinets folder not found" in result.stderr
