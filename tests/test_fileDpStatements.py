"""
tests/test_fileDpStatements.py

Production-path tests for the fileDpStatements Bash tool.

Each test builds statement PDFs shaped like the Danske Bank downloads, then
runs the real script with the real pdftotext, date, cmp and mv against
temporary folders. Only `gio` is a command double, so nothing reaches the
user's Trash.
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

SCRIPT = Path(__file__).resolve().parent.parent / "fileDpStatements"
ACCOUNT = "950246 60153699"

pytestmark = pytest.mark.skipif(
    shutil.which("pdftotext") is None, reason="pdftotext (poppler-utils) is required"
)


## helpers


def _statementWrite(path: Path, statementDate: str, account: str = ACCOUNT) -> Path:
    """Write a statement PDF laid out like page 1 of a real download."""
    return pdfWrite(
        path,
        [
            "Danske Bank",
            "Website: www.danskebank.co.uk",
            statementDate,
            f"Account number: {account}",
            f"Period this statement relates to: 01 July 2026 to {statementDate}",
        ],
    )


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Run the real script with a gio double that records trashed files."""
    fakeBin = tmp_path / "bin"
    trash = tmp_path / "trash"
    fakeBin.mkdir(exist_ok=True)
    trash.mkdir(exist_ok=True)
    gio = fakeBin / "gio"
    gio.write_text(
        f'#!/usr/bin/env bash\n[[ "$1" == trash ]] || exit 1\nmv -- "${{@: -1}}" "{trash}/"\n'
    )
    gio.chmod(0o755)

    env = dict(os.environ)
    env["PATH"] = f"{fakeBin}{os.pathsep}{env['PATH']}"
    env["LOG_UTILS"] = str(Path(organiseMyProjects.__file__).parent / "logUtils.sh")
    env["XDG_STATE_HOME"] = str(tmp_path / "state")
    env["HOME"] = str(tmp_path / "home")
    return subprocess.run(
        [
            str(SCRIPT),
            "--source",
            str(tmp_path / "src"),
            "--target",
            str(tmp_path / "dest"),
            *args,
        ],
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture
def folders(tmp_path: Path) -> Path:
    (tmp_path / "src").mkdir()
    (tmp_path / "dest").mkdir()
    (tmp_path / "home").mkdir()
    return tmp_path


## filing


def test_previewChangesNothing(folders: Path) -> None:
    # Arrange
    download = _statementWrite(
        folders / "src" / f"Statement {ACCOUNT}.PDF", "30 October 2026"
    )

    # Act
    result = _run(folders)

    # Assert
    assert result.returncode == 0, result.stderr
    assert "2026-10-30 - Direct Payments - Statement - Oct.pdf" in result.stdout
    assert download.exists()
    assert not (folders / "dest" / "2026").exists()


def test_confirmMovesStatementByStatementDate(folders: Path) -> None:
    # Arrange
    download = _statementWrite(
        folders / "src" / f"Statement {ACCOUNT} (2).PDF", "31 July 2026"
    )
    content = download.read_bytes()

    # Act
    result = _run(folders, "--confirm")

    # Assert
    target = (
        folders / "dest" / "2026" / "2026-07-31 - Direct Payments - Statement - Jul.pdf"
    )
    assert result.returncode == 0, result.stderr
    assert not download.exists()
    assert target.read_bytes() == content


def test_newYearFolderIsCreated(folders: Path) -> None:
    # Arrange
    _statementWrite(folders / "src" / f"Statement {ACCOUNT}.pdf", "29 January 2027")

    # Act
    result = _run(folders, "-y")

    # Assert
    assert result.returncode == 0, result.stderr
    assert (
        folders / "dest" / "2027" / "2027-01-29 - Direct Payments - Statement - Jan.pdf"
    ).is_file()


## duplicates and conflicts


def test_alreadyFiledUnderAnotherNameIsTrashed(folders: Path) -> None:
    # Arrange: filed earlier under its download date, not its statement date.
    download = _statementWrite(
        folders / "src" / f"Statement {ACCOUNT} (1).PDF", "31 July 2026"
    )
    yearDir = folders / "dest" / "2026"
    yearDir.mkdir()
    existing = yearDir / "2026-08-11 - Direct Payments - Statement - Jul.PDF"
    shutil.copy(download, existing)

    # Act
    result = _run(folders, "--confirm")

    # Assert
    assert result.returncode == 0, result.stderr
    assert not download.exists()
    assert (folders / "trash" / download.name).is_file()
    assert sorted(path.name for path in yearDir.iterdir()) == [existing.name]


def test_differentFileUnderTargetNameIsLeftInPlace(folders: Path) -> None:
    # Arrange
    download = _statementWrite(
        folders / "src" / f"Statement {ACCOUNT}.PDF", "31 August 2026"
    )
    yearDir = folders / "dest" / "2026"
    yearDir.mkdir()
    target = yearDir / "2026-08-31 - Direct Payments - Statement - Aug.pdf"
    target.write_bytes(b"something else")

    # Act
    result = _run(folders, "--confirm")

    # Assert
    assert result.returncode == 1
    assert download.exists()
    assert target.read_bytes() == b"something else"


## skipped downloads


def test_otherAccountIsLeftInPlace(folders: Path) -> None:
    # Arrange: name matches, but page 1 is for another account.
    download = _statementWrite(
        folders / "src" / f"Statement {ACCOUNT}.PDF",
        "30 September 2026",
        account="111111 22222222",
    )

    # Act
    result = _run(folders, "--confirm")

    # Assert
    assert result.returncode == 1
    assert download.exists()
    assert "not a Direct Payments statement" in result.stdout + result.stderr


def test_missingTargetFailsFast(folders: Path) -> None:
    # Arrange
    shutil.rmtree(folders / "dest")

    # Act
    result = _run(folders)

    # Assert
    assert result.returncode == 1
    assert "Target folder not found" in result.stderr
