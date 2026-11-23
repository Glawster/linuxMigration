"""Production path: the real pdfFiler.sh launcher and CLI.

These runs need no display: the filing window opens only when a PDF needs
it, so they use an empty inbox, an auto rule, `suggest` and `index show`.
The window itself is tested in test_window.py. HOME is temporary, so the
default config and learned.json never touch the real ones.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import MBNA_RENEWAL_LINES

LAUNCHER = Path(__file__).resolve().parents[2] / "pdfFiler.sh"
EXAMPLE_CONFIG = Path(__file__).resolve().parents[1] / "config.example.json"


def _run(tmp_path: Path, *args: str, root: Path | None = None):
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = dict(os.environ)
    env.update(
        HOME=str(home),
        XDG_STATE_HOME=str(tmp_path / "state"),
        PDF_FILER_PYTHON=sys.executable,
        DISPLAY="",  # prove no window is needed; a window would fail, not hang
    )
    command = [str(LAUNCHER), *args] + (["--root", str(root)] if root else [])
    result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=60)
    # organiseMyProjects logs to stderr; reports print to stdout.
    result.output = result.stdout + result.stderr
    return result


def _autoRule(tmp_path: Path) -> None:
    raw = json.loads(EXAMPLE_CONFIG.read_text())
    raw["rules"][0]["auto"] = True
    config = tmp_path / "home/.config/pdfFiler/config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps(raw))


_DP_LINES = [
    "Danske Bank",
    "30 October 2026",
    "Account number: 950246 60153699",
    "Period this statement relates to: 01 October 2026 to 30 October 2026",
]


def test_emptyInboxPreviewNeedsNoWindow(cabinet, tmp_path, fakeBin) -> None:
    result = _run(tmp_path, root=cabinet)

    assert result.returncode == 0, result.output
    assert "pdfs in inbox: 0" in result.output and "preview" in result.output


def test_autoRuleFilesThroughTheLauncher(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    _autoRule(tmp_path)
    pdf = inboxPdf("Statement 950246 60153699.PDF", _DP_LINES)
    target = (
        cabinet / "Benefits/Bank Statements/2026/2026-10-30 - Direct Payments - Statement - Oct.pdf"
    )

    preview = _run(tmp_path, root=cabinet)
    assert preview.returncode == 0, preview.output
    assert pdf.exists() and not target.exists()

    confirmed = _run(tmp_path, "--confirm", root=cabinet)
    assert confirmed.returncode == 0, confirmed.output
    assert target.is_file() and not pdf.exists()
    assert "filed: 1" in confirmed.output


def test_suggestCommandChangesNothing(cabinet, inboxPdf, tmp_path, fakeBin) -> None:
    pdf = inboxPdf("renewal.pdf", MBNA_RENEWAL_LINES)

    result = _run(tmp_path, "suggest", str(pdf), root=cabinet)

    assert result.returncode == 0, result.output
    assert "file as  Insurance/MBNA/2025-10-20 - Insurance, MBNA - Renewal.pdf" in result.output
    assert "or       Finance/MBNA" in result.output
    assert pdf.exists()


def test_indexShowListsWhatWasLearned(cabinet, tmp_path, fakeBin) -> None:
    # criterion 12
    learned = tmp_path / "home/.config/pdfFiler/learned.json"
    learned.parent.mkdir(parents=True)
    learned.write_text(
        '{"identifiers": {"MBNAUKM4HAP100000001": "Insurance/MBNA"},'
        ' "conflicts": [{"identifier": "X123456", "folders": ["A", "B"]}]}'
    )

    result = _run(tmp_path, "index", "show", root=cabinet)

    assert result.returncode == 0, result.output
    assert "name     Finance/Aviva/AV1111111" in result.output
    assert "learned  Insurance/MBNA" in result.output
    assert "X123456: A, B" in result.output
    assert "label: Aviva, AV1111111" in result.output
    assert "seconds to build" in result.output


def test_missingCabinetsFails(tmp_path, fakeBin) -> None:
    result = _run(tmp_path, root=tmp_path / "missing")

    assert result.returncode == 1
    assert "Cabinets folder not found" in result.output


def test_version(tmp_path, fakeBin) -> None:
    result = _run(tmp_path, "--version")
    assert result.returncode == 0 and result.stdout.startswith("pdfFiler ")


def test_systemTmpdirIsLeftAlone(cabinet, inboxPdf, tmp_path, fakeBin, monkeypatch) -> None:
    # 1.4a6 bug 3: the old script deleted whatever TMPDIR pointed at
    systemTmp = tmp_path / "systemTmp"
    systemTmp.mkdir()
    (systemTmp / "keep.txt").write_text("keep")
    monkeypatch.setenv("TMPDIR", str(systemTmp))
    _autoRule(tmp_path)
    inboxPdf("Statement 950246 60153699.PDF", _DP_LINES)

    result = _run(tmp_path, "-y", root=cabinet)

    assert result.returncode == 0, result.output
    assert (systemTmp / "keep.txt").read_text() == "keep"
