"""The cabinet index learns from names only (ADR 012, criterion 11)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from pdfFiler.cabinet import cabinetIndexBuild, filedNameParse, folderLabel, identifiersFind


@pytest.mark.parametrize(
    "name, expected",
    [
        ("2025-05-14 - Aviva, AV1111111 - Letter From 1.pdf", ("Aviva, AV1111111", "Letter From")),
        (
            "2020-05-14 - Aviva, AV1111111 - Letter From (2).pdf",
            ("Aviva, AV1111111", "Letter From"),
        ),
        ("2026-10-30 - Direct Payments - Statement - Oct.pdf", ("Direct Payments", "Statement")),
        ("2026-01-31 -Direct Payments - Statement - Jan.PDF", ("Direct Payments", "Statement")),
        ("2002-02-12 - MBNA.pdf", ("MBNA", None)),
        ("wilsona aviva illustration.pdf", None),
    ],
)
def test_filedNameParse(name: str, expected) -> None:
    assert filedNameParse(name) == expected


def test_identifiersFind() -> None:
    assert identifiersFind("Aviva, AV1111111 ref 950246 60153699 BT25 abc123") == {
        "AV1111111",
        "60153699",
        "950246",
        "ABC123",
    }


def test_folderLabelUsesParentForYear() -> None:
    assert folderLabel(Path("Benefits/Bank Statements/2026")) == "Bank Statements"
    assert folderLabel(Path("Insurance/MBNA")) == "MBNA"


def test_indexLearnsIdentifiersLabelsAndTypes(cabinet: Path) -> None:
    # Act
    index = cabinetIndexBuild(cabinet)

    # Assert
    plan = Path("Finance/Aviva/AV1111111")
    assert plan in index.identifiers["AV1111111"]
    info = index.folder(plan)
    assert info.files == 5
    assert info.labelUsual() == "Aviva, AV1111111"
    assert info.types.most_common(1) == [("Statement", 3)]
    assert index.folder(Path("Insurance/MBNA")).labelUsual() == "Insurance, MBNA"


def test_indexSkipsInboxAndArchive(cabinet: Path) -> None:
    (cabinet / "Inbox" / "2026-01-01 - Inbox, AV8888888 - Statement.pdf").write_bytes(b"x")

    index = cabinetIndexBuild(cabinet)

    assert "AV9999999" not in index.identifiers
    assert "AV8888888" not in index.identifiers
    assert not any(path.parts[0] in ("Inbox", "Archive") for path in index.folders)


def test_indexOfLargeCabinetIsFastAndOpensNoPdf(tmp_path: Path) -> None:
    # Arrange: about the size of the real cabinet. The files are unreadable,
    # so any attempt to open one as a PDF would be pointless; only names count.
    root = tmp_path / "big"
    for folderNumber in range(200):
        folder = root / f"Group {folderNumber % 20}" / f"Company {folderNumber}"
        folder.mkdir(parents=True)
        for fileNumber in range(24):
            path = folder / f"2025-01-{fileNumber + 1:02d} - Company {folderNumber} - Statement.pdf"
            path.write_bytes(b"")
            path.chmod(0o000)

    # Act
    started = time.perf_counter()
    index = cabinetIndexBuild(root)
    seconds = time.perf_counter() - started

    # Assert
    assert sum(info.files for info in index.folders.values()) == 4800
    assert seconds < 2
