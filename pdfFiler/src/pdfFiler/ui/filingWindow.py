"""The filing window: page view on the left, the filled-in form on the right.

One window is reused for every PDF in a run. `decide()` shows a form and
returns the user's Decision: File, Skip or Stop.
"""

from __future__ import annotations

import datetime as dt
import tempfile
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox, ttk

from pdfFiler.cabinet import CabinetIndex
from pdfFiler.form import (
    FILE,
    SKIP,
    STOP,
    Decision,
    FormCheck,
    FormState,
    formCheck,
    formFolderSet,
    formTypeSet,
)
from pdfFiler.ui.pageView import PageView

_PREVIEW_BANNER = "Preview: nothing will move. Run with --confirm to file."
_RED = "#b00020"
_AMBER = "#8a5a00"


class FilingWindow:
    """File, Skip or Stop for each PDF, with every field editable."""

    def __init__(self, index: CabinetIndex, today: dt.date, dryRun: bool) -> None:
        self.index = index
        self.today = today
        self.dryRun = dryRun
        self.root = tk.Tk(className="pdfFiler")
        self._scratch = Path(tempfile.mkdtemp(prefix="pdfFiler-"))
        self._state: FormState | None = None
        self._check: FormCheck | None = None
        self._decision: Decision | None = None
        self._createLayout()

    ## public

    def close(self) -> None:
        """Close the window and remove its page images."""
        try:
            self.root.destroy()
        except tk.TclError:
            pass
        for path in self._scratch.glob("*"):
            path.unlink()
        self._scratch.rmdir()

    def decide(self, state: FormState, position: int, total: int) -> Decision:
        """Show one PDF's form and wait for File, Skip or Stop."""
        self._state = state
        self._decision = None
        self.root.title(f"pdfFiler - {state.pdf.name} ({position} of {total})")
        self._titleLabel.configure(text=f"{state.pdf.name}   ({position} of {total})")
        self._fieldsShow()
        self.root.deiconify()
        self.root.lift()
        self.pageView.load(state.pdf)
        self.folderBox.focus_set()
        self.root.mainloop()
        return self._decision or Decision(STOP)

    def message(self, kind: str, text: str) -> None:
        """Show an info, warning or error message over the window."""
        show = {"error": messagebox.showerror, "warning": messagebox.showwarning}.get(
            kind, messagebox.showinfo
        )
        show("pdfFiler", text, parent=self.root)

    ## layout

    def _createLayout(self) -> None:
        self.root.geometry("1500x950+40+40")
        self.root.minsize(1100, 700)
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        family = _familyChoose(self.root)
        for name in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont"):
            font.nametofont(name).configure(family=family, size=11)
        self._boldFont = font.Font(self.root, family=family, size=11, weight="bold")
        self.root.protocol("WM_DELETE_WINDOW", lambda: self._decide(STOP))
        self.root.bind("<Return>", lambda _event: self._fileIfReady())
        self.root.bind("<KP_Enter>", lambda _event: self._fileIfReady())
        self.root.bind("<Escape>", lambda _event: self._decide(SKIP))

        self._createHeader()
        body = ttk.PanedWindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.pageView = PageView(body, self._scratch)
        body.add(self.pageView, weight=1)
        side = ttk.Frame(body, padding=(14, 0, 0, 0))
        body.add(side, weight=1)
        self._createForm(side)
        self._createFooter(side)

    def _createHeader(self) -> None:
        header = ttk.Frame(self.root, padding=(10, 10, 10, 6))
        header.pack(fill="x")
        self._titleLabel = ttk.Label(header, font=self._boldFont)
        self._titleLabel.pack(side="left")
        if self.dryRun:
            tk.Label(header, text=_PREVIEW_BANNER, background="#fff3c4", foreground="#5c4400",
                     padx=10, pady=3).pack(side="right")  # fmt: skip

    def _createForm(self, parent: ttk.Frame) -> None:
        form = ttk.Frame(parent)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Folder").grid(row=0, column=0, sticky="w", pady=4)
        self.folderBox = ttk.Combobox(form)
        self.folderBox.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(form, text="Browse…", command=self._folderBrowse).grid(
            row=0, column=2, padx=(6, 0)
        )
        self.folderBox.bind("<<ComboboxSelected>>", lambda _event: self._folderChanged())
        self.folderBox.bind("<KeyRelease>", self._keyed(self._folderChanged))

        ttk.Label(form, text="Type").grid(row=1, column=0, sticky="w", pady=4)
        self.typeBox = ttk.Combobox(form)
        self.typeBox.grid(row=1, column=1, columnspan=2, sticky="ew", pady=4)
        self.typeBox.bind("<<ComboboxSelected>>", lambda _event: self._typeChanged())
        self.typeBox.bind("<KeyRelease>", self._keyed(self._typeChanged))

        ttk.Label(form, text="Date").grid(row=2, column=0, sticky="w", pady=4)
        self.dateEntry = ttk.Entry(form, width=14)
        self.dateEntry.grid(row=2, column=1, sticky="w", pady=4)
        self.dateEntry.bind(
            "<KeyRelease>", self._keyed(lambda: self._typed("date", self.dateEntry))
        )

        ttk.Label(form, text="Label").grid(row=3, column=0, sticky="w", pady=4)
        self.labelEntry = ttk.Entry(form)
        self.labelEntry.grid(row=3, column=1, columnspan=2, sticky="ew", pady=4)
        self.labelEntry.bind(
            "<KeyRelease>", self._keyed(lambda: self._typed("label", self.labelEntry))
        )

        ttk.Separator(parent).pack(fill="x", pady=12)
        ttk.Label(parent, text="File as").pack(anchor="w")
        # One line, the full path; it scrolls rather than wrapping.
        self.fileAsVar = tk.StringVar()
        self.fileAsEntry = ttk.Entry(parent, textvariable=self.fileAsVar, state="readonly",
                                     font=self._boldFont)  # fmt: skip
        self.fileAsEntry.pack(fill="x", pady=(2, 6))
        self.statusLabel = ttk.Label(parent, wraplength=640, justify="left")
        self.statusLabel.pack(anchor="w", pady=(0, 10))
        ttk.Label(parent, text="Why suggested").pack(anchor="w")
        self.whyLabel = ttk.Label(parent, wraplength=640, justify="left", foreground="#444444")
        self.whyLabel.pack(anchor="w", pady=(2, 0))

    def _createFooter(self, parent: ttk.Frame) -> None:
        footer = ttk.Frame(parent)
        footer.pack(side="bottom", fill="x", pady=(10, 0))
        ttk.Label(footer, text="Enter = File    Esc = Skip", foreground="#666666").pack(side="left")
        self.fileButton = ttk.Button(footer, text="File", command=self._fileIfReady)
        self.fileButton.pack(side="right")
        ttk.Button(footer, text="Skip", command=lambda: self._decide(SKIP)).pack(
            side="right", padx=6
        )
        ttk.Button(footer, text="Stop", command=lambda: self._decide(STOP)).pack(side="right")

    ## fields

    def _fieldsShow(self) -> None:
        """Copy the form state into the widgets."""
        state = self._state
        self.folderBox.configure(values=state.folderChoices)
        _entrySet(self.folderBox, state.folder)
        self.typeBox.configure(values=state.typeChoices)
        _entrySet(self.typeBox, state.docType)
        _entrySet(self.dateEntry, state.date)
        _entrySet(self.labelEntry, state.label)
        self.whyLabel.configure(text="; ".join(state.reasons))
        self._refresh()

    def _folderChanged(self) -> None:
        formFolderSet(self._state, self.folderBox.get(), self.index, self.today)
        self.typeBox.configure(values=self._state.typeChoices)
        _entrySet(self.typeBox, self._state.docType)
        _entrySet(self.dateEntry, self._state.date)
        _entrySet(self.labelEntry, self._state.label)
        self._refresh()

    def _typeChanged(self) -> None:
        formTypeSet(self._state, self.typeBox.get(), self.today)
        _entrySet(self.dateEntry, self._state.date)
        self._refresh()

    def _typed(self, name: str, entry: ttk.Entry) -> None:
        setattr(self._state, name, entry.get())
        self._state.edited.add(name)
        self._refresh()

    def _refresh(self) -> None:
        """Show the one-line destination and anything stopping the file."""
        check = formCheck(self._state, self.today)
        self._check = check
        self.fileAsVar.set(check.shown or "—")
        self.fileAsEntry.xview_moveto(0)
        if check.problem:
            self.statusLabel.configure(text=check.problem, foreground=_RED)
            self.fileButton.configure(text="File", state="disabled")
        elif check.outcome == "duplicate":
            self.statusLabel.configure(
                text=f"Already filed as {check.existing.name}: this scan will go to the Trash.",
                foreground=_AMBER,
            )
            self.fileButton.configure(text="Trash duplicate", state="normal")
        else:
            self.statusLabel.configure(text="")
            self.fileButton.configure(text="File", state="normal")

    ## actions

    def _decide(self, action: str) -> None:
        self._decision = Decision(action, self._check if action == FILE else None)
        self.root.quit()

    def _fileIfReady(self) -> None:
        if self._check is not None and self._check.problem is None:
            self._decide(FILE)

    def _folderBrowse(self) -> None:
        root = self._state.root
        start = root / self._state.folder if self._state.folder else root
        chosen = filedialog.askdirectory(
            parent=self.root,
            initialdir=str(start if start.is_dir() else root),
            mustexist=True,
            title="Choose filing folder",
        )
        if not chosen:
            return
        chosenPath = Path(chosen).resolve()
        if root.resolve() not in chosenPath.parents:
            self.message("error", f"The folder must be inside {root}")
            return
        _entrySet(self.folderBox, chosenPath.relative_to(root.resolve()).as_posix())
        self._folderChanged()

    def _keyed(self, action):
        """Run an action on typing, but not for keys handled by the window."""

        def handler(event: tk.Event) -> None:
            if event.keysym not in ("Return", "KP_Enter", "Escape", "Tab"):
                action()

        return handler


## utilities

# Tk without Xft support (conda's default build) sees only X core fonts;
# texgyreheros is the best sans among them.
_FAMILIES = (
    "Ubuntu",
    "DejaVu Sans",
    "Noto Sans",
    "Cantarell",
    "Liberation Sans",
    "texgyreheros",
    "latin modern sans",
)


def _familyChoose(root: tk.Misc) -> str:
    available = {name.casefold(): name for name in font.families(root)}
    for family in _FAMILIES:
        if family.casefold() in available:
            return available[family.casefold()]
    return font.nametofont("TkDefaultFont").cget("family")


def _entrySet(widget: ttk.Entry, value: str) -> None:
    if widget.get() != value:
        widget.delete(0, "end")
        widget.insert(0, value)
