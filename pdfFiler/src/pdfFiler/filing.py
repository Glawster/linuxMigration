"""Move a PDF into the cabinet safely (the 1.4a6 rules, kept by criterion 10).

Nothing is overwritten or deleted: identical content already in the folder
sends the PDF to the desktop Trash, and a different file under the new name
leaves the PDF where it is.
"""

from __future__ import annotations

import filecmp
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


class FilingError(RuntimeError):
    """A move that did not complete; the original is kept."""


@dataclass(frozen=True)
class FilingCheck:
    """What filing a PDF at a destination would do."""

    outcome: str  # "file", "duplicate" or "conflict"
    existing: Path | None = None


## filing


def filingCheck(pdf: Path, destination: Path) -> FilingCheck:
    """Decide between filing, already filed and name taken."""
    folder = destination.parent
    if folder.is_dir():
        for existing in sorted(folder.iterdir()):
            if existing.is_file() and filecmp.cmp(pdf, existing, shallow=False):
                return FilingCheck("duplicate", existing)
    if destination.exists():
        return FilingCheck("conflict", destination)
    return FilingCheck("file")


def filingMove(pdf: Path, destination: Path) -> None:
    """Move a PDF to a new name that must not exist, creating the folder."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        # link + unlink never replaces an existing file, unlike rename.
        os.link(pdf, destination)
        pdf.unlink()
    except FileExistsError as error:
        raise FilingError(f"{destination} appeared while filing; original kept") from error
    except OSError:
        # A different filesystem: copy without overwriting, then verify.
        with pdf.open("rb") as source, destination.open("xb") as target:
            target.write(source.read())
        if not filecmp.cmp(pdf, destination, shallow=False):
            destination.unlink()
            raise FilingError(f"copy to {destination} did not verify; original kept") from None
        pdf.unlink()


def filingTrash(pdf: Path) -> None:
    """Send a PDF to the desktop Trash with gio."""
    result = subprocess.run(["gio", "trash", "--", str(pdf)], capture_output=True, text=True)
    if result.returncode != 0:
        raise FilingError(f"gio trash failed for {pdf}: {result.stderr.strip()}")


def inboxList(inbox: Path) -> list[Path]:
    """The inbox PDFs (.pdf or .PDF), oldest first, then by name."""
    pdfs = [path for path in inbox.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"]
    return sorted(pdfs, key=lambda path: (path.stat().st_mtime, path.name))
