"""A widget showing one page of a PDF, fitted to its height, with paging and zoom."""

from __future__ import annotations

import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import ttk

_ZOOM_DPI = 150


class PageView(ttk.Frame):
    """Page images rendered by pdftoppm into a private scratch folder."""

    def __init__(self, parent: tk.Misc, scratch: Path) -> None:
        super().__init__(parent)
        self._scratch = scratch
        self._pdf: Path | None = None
        self._page = 1
        self._pages = 1
        self._zoomed = False
        self._image: tk.PhotoImage | None = None  # keep a reference for Tk
        self._createToolbar()
        self._createCanvas()

    ## public

    def load(self, pdf: Path) -> None:
        """Show page 1 of a PDF, fitted to the view."""
        self._pdf = pdf
        self._page = 1
        self._pages = _pageCount(pdf)
        self._zoomed = False
        self.render()

    def render(self) -> None:
        """Render the current page at fit or zoom size."""
        if self._pdf is None:
            return
        self.update_idletasks()
        output = self._scratch / "page"
        size = (
            ["-r", str(_ZOOM_DPI)]
            if self._zoomed
            else ["-scale-to-y", str(max(self._canvas.winfo_height(), 600)), "-scale-to-x", "-1"]
        )
        result = subprocess.run(
            ["pdftoppm", "-png", "-singlefile", "-f", str(self._page), "-l", str(self._page)]
            + size
            + [str(self._pdf), str(output)],
            capture_output=True,
        )
        self._canvas.delete("all")
        image = output.with_suffix(".png")
        if result.returncode != 0 or not image.is_file():
            self._canvas.create_text(20, 20, anchor="nw", text="Page could not be shown")
            self._image = None
        else:
            self._image = tk.PhotoImage(file=str(image))
            self._canvas.create_image(0, 0, anchor="nw", image=self._image)
            self._canvas.configure(scrollregion=(0, 0, self._image.width(), self._image.height()))
        self._pageLabel.configure(text=f"Page {self._page} of {self._pages}")
        self._zoomButton.configure(text="Fit" if self._zoomed else "Zoom")

    ## layout

    def _createCanvas(self) -> None:
        holder = ttk.Frame(self)
        holder.pack(fill="both", expand=True)
        self._canvas = tk.Canvas(holder, background="#808080", highlightthickness=0, cursor="hand2")
        vertical = ttk.Scrollbar(holder, orient="vertical", command=self._canvas.yview)
        horizontal = ttk.Scrollbar(holder, orient="horizontal", command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self._canvas.bind("<Button-1>", lambda _event: self._zoomToggle())
        self._canvas.bind("<Button-4>", lambda _event: self._canvas.yview_scroll(-3, "units"))
        self._canvas.bind("<Button-5>", lambda _event: self._canvas.yview_scroll(3, "units"))

    def _createToolbar(self) -> None:
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 4))
        ttk.Button(toolbar, text="◀", width=3, command=lambda: self._pageMove(-1)).pack(side="left")
        self._pageLabel = ttk.Label(toolbar, text="Page 1 of 1", padding=(8, 0))
        self._pageLabel.pack(side="left")
        ttk.Button(toolbar, text="▶", width=3, command=lambda: self._pageMove(1)).pack(side="left")
        self._zoomButton = ttk.Button(toolbar, text="Zoom", command=self._zoomToggle)
        self._zoomButton.pack(side="right")

    ## actions

    def _pageMove(self, step: int) -> None:
        page = min(max(self._page + step, 1), self._pages)
        if page != self._page:
            self._page = page
            self.render()

    def _zoomToggle(self) -> None:
        self._zoomed = not self._zoomed
        self.render()


## utilities


def _pageCount(pdf: Path) -> int:
    result = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return max(int(line.split()[1]), 1)
    return 1
