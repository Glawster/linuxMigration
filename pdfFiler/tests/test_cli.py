"""Production path: the real pdfFiler.sh launcher and CLI.

zenity, feh, wmctrl and gio are command doubles (fakeBin); zenity answers
from PDF_ZENITY_* variables and records each dialog. HOME is temporary, so
the default config and learned.json never touch the real ones.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import AVIVA_TAX_LINES, MBNA_RENEWAL_LINES

LAUNCHER = Path(__file__).resolve().parents[2] / "pdfFiler.sh"

_ZENITY = r"""#!/usr/bin/env bash
# zenity double: answers from PDF_ZENITY_* and logs each dialog kind.
echo "$1" >>"$PDF_ZENITY_LOG"
case "$1" in
    --question)
        if [[ "$*" == *--extra-button=Skip* ]]; then
            case "${PDF_ZENITY_SUGGESTION:-file}" in
                file) exit 0 ;;
                skip) echo Skip; exit 1 ;;
                *) exit 1 ;;
            esac
        fi
        exit "${PDF_ZENITY_PROCEED:-0}" ;;
    --file-selection) [[ -n "${PDF_ZENITY_FOLDER:-}" ]] || exit 1; echo "$PDF_ZENITY_FOLDER" ;;
    --list) echo "${PDF_ZENITY_TYPE:-Invoice}" ;;
    --entry) [[ -n "${PDF_ZENITY_DATE:-}" ]] || exit 1; echo "$PDF_ZENITY_DATE" ;;
    *) exit 0 ;;
esac
"""


def _run(cabinet: Path, tmp_path: Path, fakeBin: Path, *args: str, **answers: str):
    zenity = fakeBin / "zenity"
    zenity.write_text(_ZENITY)
    zenity.chmod(0o755)
    dialogLog = tmp_path / "dialogs.log"
    dialogLog.write_text("")
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = dict(os.environ)
    env.update(
        HOME=str(home),
        XDG_STATE_HOME=str(tmp_path / "state"),
        PDF_FILER_PYTHON=sys.executable,
        PDF_ZENITY_LOG=str(dialogLog),
        **{f"PDF_ZENITY_{key.upper()}": value for key, value in answers.items()},
    )
    result = subprocess.run(
        (
            [str(LAUNCHER), *args, "--root", str(cabinet)]
            if args[:1] != ("--version",)
            else [str(LAUNCHER), *args]
        ),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    # organiseMyProjects logs to stderr; reports print to stdout.
    result.output = result.stdout + result.stderr
    return result, dialogLog.read_text().split()


def test_previewByDefaultMovesNothing(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    pdf = inboxPdf("2026-11-23.pdf", AVIVA_TAX_LINES)

    result, dialogs = _run(cabinet, tmp_path, fakeBin)

    assert result.returncode == 0, result.stderr
    assert pdf.exists()
    assert "Finance/Aviva/AV1111111/2026-04-05 - Aviva, AV1111111 - Tax.pdf" in result.output
    assert "preview" in result.output
    assert dialogs.count("--question") == 1


def test_confirmFilesSuggestionAndLearns(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)

    result, _ = _run(cabinet, tmp_path, fakeBin, "--confirm")

    assert result.returncode == 0, result.stderr
    assert (cabinet / "Insurance/MBNA/2025-10-20 - Insurance, MBNA - Renewal.pdf").is_file()
    learned = tmp_path / "home/.config/pdfFiler/learned.json"
    assert "MBNAUKM4HAP100000001" in learned.read_text()


def test_skipButtonLeavesPdf(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    pdf = inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)

    result, _ = _run(cabinet, tmp_path, fakeBin, "-y", suggestion="skip")

    assert result.returncode == 0, result.stderr
    assert pdf.exists()
    assert "skipped: 1" in result.output


def test_changeWithCancelledFolderStopsRun(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    pdf = inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)

    result, dialogs = _run(cabinet, tmp_path, fakeBin, "-y", suggestion="change")

    assert result.returncode == 0, result.stderr
    assert pdf.exists()
    assert dialogs == ["--question", "--file-selection"]
    assert "cancelled by user" in result.output


def test_suggestCommandChangesNothing(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    pdf = inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)

    result, dialogs = _run(cabinet, tmp_path, fakeBin, "suggest", str(pdf))

    assert result.returncode == 0, result.stderr
    assert "file as  Insurance/MBNA/2025-10-20 - Insurance, MBNA - Renewal.pdf" in result.output
    assert "or       Finance/MBNA" in result.output
    assert pdf.exists() and dialogs == []


def test_indexShowListsWhatWasLearned(cabinet, tmp_path, fakeBin) -> None:
    # criterion 12
    learned = tmp_path / "home/.config/pdfFiler/learned.json"
    learned.parent.mkdir(parents=True)
    learned.write_text(
        '{"identifiers": {"MBNAUKM4HAP100000001": "Insurance/MBNA"},'
        ' "conflicts": [{"identifier": "X123456", "folders": ["A", "B"]}]}'
    )

    result, _ = _run(cabinet, tmp_path, fakeBin, "index", "show")

    assert result.returncode == 0, result.stderr
    assert "AV1111111" in result.output and "name     Finance/Aviva/AV1111111" in result.output
    assert "learned  Insurance/MBNA" in result.output
    assert "X123456: A, B" in result.output
    assert "label: Aviva, AV1111111" in result.output
    assert "seconds to build" in result.output


def test_missingCabinetsFails(tmp_path, fakeBin) -> None:
    result, _ = _run(tmp_path / "missing", tmp_path, fakeBin)

    assert result.returncode == 1
    assert "Cabinets folder not found" in result.output + result.stderr


def test_versionAndHelp(tmp_path, fakeBin, cabinet) -> None:
    version, _ = _run(cabinet, tmp_path, fakeBin, "--version")
    assert version.returncode == 0 and version.stdout.startswith("pdfFiler ")


def test_systemTmpdirIsLeftAlone(cabinet, inboxPdf, tmp_path, fakeBin, monkeypatch) -> None:
    # 1.4a6 bug 3: the old script deleted whatever TMPDIR pointed at
    systemTmp = tmp_path / "systemTmp"
    systemTmp.mkdir()
    (systemTmp / "keep.txt").write_text("keep")
    monkeypatch.setenv("TMPDIR", str(systemTmp))
    inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)

    result, _ = _run(cabinet, tmp_path, fakeBin, "-y")

    assert result.returncode == 0, result.stderr
    assert (systemTmp / "keep.txt").read_text() == "keep"
    assert not [path for path in systemTmp.iterdir() if path.name.startswith("pdfFiler-")]
