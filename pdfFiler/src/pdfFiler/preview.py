"""Show page 1 of a PDF beside the dialogs. GUI layer."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path


class Preview:
    """A page-1 image window (feh, else eog), closed after each PDF."""

    def __init__(self) -> None:
        # A private scratch folder; never the shared TMPDIR itself (1.4a6 bug 3).
        self._scratch = Path(tempfile.mkdtemp(prefix="pdfFiler-"))
        self._process: subprocess.Popen | None = None
        self._title = ""

    def close(self) -> None:
        """Close the window and remove its image."""
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
        if self._title and shutil.which("wmctrl"):
            subprocess.run(["wmctrl", "-c", self._title], capture_output=True)
        self._process = None
        self._title = ""
        for image in self._scratch.glob("page-*.png"):
            image.unlink()

    def cleanup(self) -> None:
        """Close the window and remove the scratch folder."""
        self.close()
        shutil.rmtree(self._scratch, ignore_errors=True)

    def show(self, pdf: Path) -> bool:
        """Show page 1; False when it cannot be rendered."""
        self.close()
        rendered = subprocess.run(
            ["pdftoppm", "-png", "-f", "1", "-l", "1", str(pdf), str(self._scratch / "page")],
            capture_output=True,
        )
        images = sorted(self._scratch.glob("page-*.png"))
        if rendered.returncode != 0 or not images:
            return False
        self._title = f"pdfFiler Preview - {pdf.name}"
        if shutil.which("feh"):
            command = ["feh", "--title", self._title, "--zoom-fill", "--geometry", "700x900+20+20"]
        elif shutil.which("eog"):
            command = ["eog", "--new-instance"]
        else:
            return True
        self._process = subprocess.Popen(
            [*command, str(images[0])], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        # Place the window top-left so the dialogs do not hide it.
        time.sleep(0.3)
        if shutil.which("wmctrl"):
            subprocess.run(
                ["wmctrl", "-r", self._title, "-e", "0,20,20,700,900"], capture_output=True
            )
        return True
