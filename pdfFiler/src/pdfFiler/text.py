"""Read the text of a PDF's first pages, with OCR when it has no text layer."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

PAGES_READ = 2


## text


def textOfPdf(path: Path, pages: int = PAGES_READ) -> str:
    """Return the text of the first pages of a PDF.

    pdftotext reads the text layer. A scan with no text layer is read with
    ocrmypdf when it is installed; otherwise the text is empty.
    """
    text = _pdftotext(path, pages)
    if text.strip() or shutil.which("ocrmypdf") is None:
        return text
    return _ocrText(path, pages)


## utilities


def _ocrText(path: Path, pages: int) -> str:
    """OCR the first pages into a sidecar text file and return it."""
    with tempfile.TemporaryDirectory() as scratch:
        sidecar = Path(scratch) / "sidecar.txt"
        output = Path(scratch) / "ocr.pdf"
        subprocess.run(
            [
                "ocrmypdf",
                "--pages",
                f"1-{pages}",
                "--sidecar",
                str(sidecar),
                str(path),
                str(output),
            ],
            capture_output=True,
            check=False,
        )
        return sidecar.read_text(errors="replace") if sidecar.is_file() else ""


def _pdftotext(path: Path, pages: int) -> str:
    result = subprocess.run(
        ["pdftotext", "-f", "1", "-l", str(pages), str(path), "-"],
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    return result.stdout if result.returncode == 0 else ""
