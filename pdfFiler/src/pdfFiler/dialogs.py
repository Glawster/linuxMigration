"""zenity dialogs for `inbox file`. GUI layer: core modules never import it."""

from __future__ import annotations

import subprocess
from pathlib import Path

FILE = "file"
CHANGE = "change"
SKIP = "skip"


class Dialogs:
    """The questions `inbox file` asks, answered through zenity."""

    def dateAsk(self, prefill: str = "", problem: str = "") -> str | None:
        """Ask for a date (YYYY-MM-DD); None on cancel."""
        text = (problem + "\n\n" if problem else "") + "Enter the document date (YYYY-MM-DD):"
        result = _zenity(
            "--entry", "--title=Document Date", f"--text={text}", f"--entry-text={prefill}"
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return result.stdout.strip()

    def folderChoose(self, start: Path) -> Path | None:
        """Choose a filing folder, starting at `start`; None on cancel."""
        result = _zenity(
            "--file-selection",
            "--directory",
            "--title=Choose Filing Folder",
            f"--filename={start}/",
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return Path(result.stdout.strip())

    def message(self, kind: str, text: str) -> None:
        """Show an info, warning or error message."""
        _zenity(f"--{kind}", f"--text={text}")

    def proceedAsk(self, text: str) -> bool:
        """Ask Yes/No."""
        return _zenity("--question", f"--text={text}").returncode == 0

    def suggestionAsk(self, text: str) -> str:
        """Offer a suggestion: FILE, CHANGE or SKIP."""
        result = _zenity(
            "--question",
            "--title=File this PDF?",
            f"--text={text}",
            "--ok-label=File",
            "--cancel-label=Change…",
            "--extra-button=Skip",
        )
        if result.returncode == 0:
            return FILE
        if result.stdout.strip() == "Skip":
            return SKIP
        return CHANGE

    def typeChoose(self, pdfName: str, types: list[str]) -> str | None:
        """Choose a document type, the suggestion listed first; None on cancel."""
        result = _zenity(
            "--list",
            "--title=Document Type",
            f"--text=Choose document type for {pdfName}",
            "--column=Type",
            "--width=400",
            "--height=600",
            *types,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        return result.stdout.strip().split("|")[0]


## utilities


def _zenity(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(["zenity", *arguments], capture_output=True, text=True)
