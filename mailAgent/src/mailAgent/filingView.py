"""Compact Inbox filing workspace.

The table lists organisation domains. The editor records rules only:
it does not create folders or move mail.
"""

from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import HorizontalGroup
from textual.coordinate import Coordinate
from textual.events import DescendantBlur, Mount, MouseUp, Resize
from textual.widget import Widget
from textual.widgets import DataTable, Input, Select, Static
from textual.widgets.data_table import ColumnKey

import mailAgent.filing as filing
from mailAgent.actionGuidance import ActionNeeded
from mailAgent.senderAddress import senderNormalize

# Loaded as application CSS. Widget DEFAULT_CSS cannot override the shared sheet.
FILING_CSS = Path(__file__).with_suffix(".tcss").read_text(encoding="utf-8")
_DESTINATION_COLUMN = 5


## view


class FilingTable(DataTable):
    """Save domain dispositions with keys scoped to the focused filing table."""

    BINDINGS = [
        Binding("c", "choose_filter", "Choose/All"),
        Binding("i", "ignore", "Ignore"),
        Binding("j", "junk", "Junk"),
        Binding("f", "file", "File"),
        Binding("s", "sender_edit", "Sender"),
    ]

    def action_choose_filter(self) -> None:
        """Toggle between every filing row and only rows that still need Choose."""
        if isinstance(self.parent, FilingView):
            self.parent.chooseToggle()

    def action_ignore(self) -> None:
        """Save Ignore for the selected domain, without changing mail."""
        self._dispositionChoose("ignore")

    def action_junk(self) -> None:
        """Save Junk for the selected domain, without changing mail."""
        self._dispositionChoose("junk")

    def action_file(self) -> None:
        """Open folder choices; File requires a destination before saving."""
        self._dispositionChoose("file")

    def action_sender_edit(self) -> None:
        """Reveal exact sender editing for the selected domain."""
        if isinstance(self.parent, FilingView):
            self.parent.query_one(FilingEditor).action_sender_edit()

    def _dispositionChoose(self, disposition: str) -> None:
        view = self.parent
        if isinstance(view, FilingView) and view._selectedRow() is not None:
            editor = view.query_one(FilingEditor)
            if disposition == "file":
                targets = view.selectedRows() or [view._selectedRow()]
                if any(
                    str(row.get("disposition") or "").lower() in ("ignore", "junk")
                    for row in targets
                    if row
                ):
                    editor.dispositionClear()
                else:
                    editor.dispositionSet("file")
                view.query_one("#filing-parent").focus()
            else:
                editor.dispositionSet(disposition)
                editor._ruleSave("domain")
                self.focus()


class FilingView(Widget):
    """Domain table with a compact rule editor beneath it."""

    def __init__(self, snapshot: dict, issue: str | None = None) -> None:
        """Keep the shared snapshot. Saves write rules, then replace its plan."""
        super().__init__()
        self.snapshot = snapshot
        self.issue = issue
        plan = snapshot.get("filingPlan") or {}
        self._allRows: list[dict] = list(plan.get("rows") or [])
        self._chooseOnly = False
        self._marked: set[tuple[str, str]] = set()
        self._selectionAnchor: tuple[str, str] | None = None
        self.rows: list[dict] = self._rowsVisible()
        self._widths: dict[str, int] = {}
        self._columnKeys: dict[str, ColumnKey] = {}
        self._fitting = False

    def compose(self) -> ComposeResult:
        """One summary line, a scrolling table, then the editor."""
        plan = self._plan()
        actionText = _actionText(self._allRows)
        yield ActionNeeded(
            self._summaryDisplay(),
            id="filing-summary",
            classes="warning action-needed" if actionText else "",
            markup=False,
        )
        if self.issue:
            yield Static(self.issue, id="filing-issue", markup=False)
        table = FilingTable(id="filing-table", cursor_type="row")
        for key, label, width in _columnSpecs():
            self._columnKeys[key] = table.add_column(label, width=width, key=key)
        for row in self.rows:
            table.add_row(*_tableCells(row, 16, self._identity(row) in self._marked))
        yield table
        empty = Static(
            "" if self.rows else "No Inbox domains to file",
            id="filing-empty",
            markup=False,
        )
        empty.display = not self.rows
        yield empty
        yield FilingEditor(id="filing-editor")
        overrides = Static(_overrideText(plan), id="filing-overrides", markup=False)
        overrides.display = bool(plan.get("senderOverrides"))
        yield overrides

    def actionNavigate(self) -> None:
        """Select the first unresolved domain and focus its decision field."""
        choices = [index for index, row in enumerate(self.rows) if _rowNeedsChoice(row)]
        pending = choices or [
            index for index, row in enumerate(self.rows) if _rowNeedsAction(row)
        ]
        if not pending:
            return
        index = pending[0]
        row = self.rows[index]
        self.query_one("#filing-table", DataTable).move_cursor(row=index)
        self.query_one(FilingEditor).rowShow(row, self._plan())
        target = (
            "#filing-domain"
            if row.get("domainUncertain")
            else ("#filing-parent" if _rowNeedsChoice(row) else "#filing-child")
        )
        self.query_one(target).focus()

    def chooseToggle(self) -> None:
        """Toggle the table between all rows and only unresolved Choose rows."""
        table = self.query_one("#filing-table", DataTable)
        previous = self._selectedIdentity()
        previousScroll = table.scroll_y
        self._chooseOnly = not self._chooseOnly
        self.rows = self._rowsVisible()
        destinationWidth = self._widths.get("destination", 16)
        with table.prevent(DataTable.RowHighlighted):
            table.clear(columns=False)
            for row in self.rows:
                table.add_row(
                    *_tableCells(
                        row,
                        destinationWidth,
                        self._identity(row) in self._marked,
                    )
                )
            self._cursorRestore(previous)
        self._summaryUpdate()
        self._emptyUpdate()
        self._editorSync()
        self.columnsFit()
        self._viewportRestore(previousScroll)

    def planShow(self) -> None:
        """Reload the table while keeping the selected domain and viewport."""
        table = self.query_one("#filing-table", DataTable)
        previous = self._selectedIdentity()
        previousScroll = table.scroll_y
        plan = self._plan()
        self._allRows = list(plan.get("rows") or [])
        valid = {self._identity(row) for row in self._allRows}
        self._marked.intersection_update(valid)
        if self._selectionAnchor not in valid:
            self._selectionAnchor = None
        self.rows = self._rowsVisible()
        destinationWidth = self._widths.get("destination", 16)
        with table.prevent(DataTable.RowHighlighted):
            table.clear(columns=False)
            for row in self.rows:
                table.add_row(
                    *_tableCells(
                        row,
                        destinationWidth,
                        self._identity(row) in self._marked,
                    )
                )
            self._cursorRestore(previous)
        self._summaryUpdate()
        self._overridesShow(plan)
        self._emptyUpdate()
        self._editorSync()
        self.columnsFit()
        self._viewportRestore(previousScroll)

    def planRecompute(self) -> None:
        """Rebuild the plan from saved rules. This does not rescan mail."""
        context = self.snapshot.get("filingContext")
        if not context:
            raise ValueError("Filing context is unavailable")
        self.snapshot["filingPlan"] = filing.filingPlanBuild(
            context, self.snapshot, filing.filingRulesLoad(filing.filingPath())
        )
        self.planShow()

    def columnsFit(self) -> None:
        """Give Domain most of the spare width and clip Destination."""
        if self._fitting:
            return
        table = self.query_one("#filing-table", DataTable)
        if not self._columnKeys or not table.is_mounted:
            return
        available = table.scrollable_content_region.width
        if available < 24:
            return
        widths = _columnWidths(available, table.cell_padding)
        if widths == self._widths:
            return
        self._fitting = True
        try:
            self._widths = widths
            previous = self._selectedIdentity()
            previousScroll = table.scroll_y
            with table.prevent(DataTable.RowHighlighted):
                table.clear(columns=True)
                for name, label, _width in _columnSpecs():
                    self._columnKeys[name] = table.add_column(
                        label, width=widths[name], key=name
                    )
                for row in self.rows:
                    table.add_row(
                        *_tableCells(
                            row,
                            widths["destination"],
                            self._identity(row) in self._marked,
                        )
                    )
                self._cursorRestore(previous)
            self._destinationsClip()
            self._viewportRestore(previousScroll)
        finally:
            self._fitting = False

    @on(Mount)
    def viewMounted(self, event: Mount) -> None:
        """Fill the editor and fit columns once the tab has a real size."""
        del event
        self.call_after_refresh(self._editorSync)
        self.call_after_refresh(self.columnsFit)

    @on(Resize)
    def viewResized(self, event: Resize) -> None:
        """Refit columns when the terminal size changes, without resetting edits."""
        del event
        self.call_after_refresh(self.columnsFit)

    @on(MouseUp, "#filing-table")
    def tableMouseUp(self, event: MouseUp) -> None:
        """Apply desktop-style Ctrl/Shift selection after the table moves its cursor."""
        if getattr(event, "button", 1) != 1:
            return
        row = self._selectedRow()
        if not row:
            return
        identity = self._identity(row)
        control = bool(getattr(event, "ctrl", False))
        shift = bool(getattr(event, "shift", False))
        if shift:
            self._rangeMark(identity, additive=control)
        elif control:
            if identity in self._marked:
                self._marked.remove(identity)
            else:
                self._marked.add(identity)
            self._selectionAnchor = identity
        else:
            self._marked.clear()
            self._selectionAnchor = identity
        self._selectionRender()

    @on(DataTable.RowHighlighted, "#filing-table")
    def rowHighlighted(self, event: DataTable.RowHighlighted) -> None:
        """Keep the editor on the highlighted domain or active multi-selection."""
        event.stop()
        if not self.query("#filing-editor"):
            return
        if self._marked:
            self._editorSync()
            return
        row = None
        if 0 <= event.cursor_row < len(self.rows):
            row = self.rows[event.cursor_row]
        self.query_one(FilingEditor).rowShow(row, self._plan())

    def selectedRows(self) -> list[dict]:
        """Return explicitly Ctrl/Shift-selected rows in stable plan order."""
        if not self._marked:
            return []
        return [row for row in self._allRows if self._identity(row) in self._marked]

    def _rangeMark(self, identity: tuple[str, str], additive: bool) -> None:
        """Mark the visible range from the anchor through the clicked row."""
        identities = [self._identity(row) for row in self.rows]
        anchor = self._selectionAnchor
        if anchor not in identities:
            anchor = identity
        start = identities.index(anchor)
        end = identities.index(identity)
        low, high = sorted((start, end))
        selected = set(identities[low : high + 1])
        if additive:
            self._marked.update(selected)
        else:
            self._marked = selected
        self._selectionAnchor = anchor

    def _selectionRender(self) -> None:
        """Refresh visible selection marks and the editor without rebuilding rows."""
        table = self.query_one("#filing-table", DataTable)
        for index, row in enumerate(self.rows):
            if index >= table.row_count:
                break
            table.update_cell_at(
                Coordinate(index, 0),
                _domainCell(row, self._identity(row) in self._marked),
                update_width=False,
            )
        self._editorSync()

    def _plan(self) -> dict:
        """Return the filing plan currently stored on the snapshot."""
        return self.snapshot.get("filingPlan") or {}

    def _rowsVisible(self) -> list[dict]:
        """Return either all plan rows or only rows whose action is Choose."""
        if not self._chooseOnly:
            return list(self._allRows)
        return [row for row in self._allRows if _rowAction(row) == "Choose"]

    def _summaryDisplay(self) -> str:
        """Describe outstanding work plus the current table filter."""
        base = _actionText(self._allRows) or _summaryText()
        view = "Choose only" if self._chooseOnly else "All"
        return f"{base} · View: {view} ({len(self.rows)}/{len(self._allRows)})"

    def _summaryUpdate(self) -> None:
        """Refresh the top guidance and warning styling."""
        actionText = _actionText(self._allRows)
        action = self.query_one("#filing-summary", Static)
        action.update(self._summaryDisplay())
        action.set_class(bool(actionText), "warning")
        action.set_class(bool(actionText), "action-needed")

    def _emptyUpdate(self) -> None:
        """Show the empty message for the active filter."""
        empty = self.query_one("#filing-empty", Static)
        message = ""
        if not self.rows:
            message = (
                "No domains need Choose"
                if self._chooseOnly
                else "No Inbox domains to file"
            )
        empty.update(message)
        empty.display = not self.rows

    def _editorSync(self) -> None:
        """Show the active multi-selection or whichever domain the cursor is on."""
        if not self.query("#filing-editor"):
            return
        editor = self.query_one(FilingEditor)
        marked = self.selectedRows()
        if marked:
            editor.rowsShow(marked, self._plan())
        else:
            editor.rowShow(self._selectedRow(), self._plan())

    def _overridesShow(self, plan: dict) -> None:
        """Show exact sender overrides only when at least one exists."""
        widget = self.query_one("#filing-overrides", Static)
        text = _overrideText(plan)
        widget.update(text)
        widget.display = bool(text)

    def _selectedRow(self) -> dict | None:
        """Return the domain under the cursor, or the first visible domain."""
        if not self.rows or not self.query("#filing-table"):
            return None
        table = self.query_one("#filing-table", DataTable)
        row = table.cursor_row
        if not isinstance(row, int) or row < 0 or row >= len(self.rows):
            row = 0
        return self.rows[row]

    @staticmethod
    def _identity(row: dict) -> tuple[str, str]:
        """Return the stable mailbox/domain identity for one filing row."""
        return str(row.get("mailbox") or ""), str(row.get("domain") or "")

    def _selectedIdentity(self) -> tuple[str, str] | None:
        """Return the selected mailbox and domain, if a row is selected."""
        row = self._selectedRow()
        return self._identity(row) if row else None

    def _cursorRestore(self, previous: tuple[str, str] | None) -> None:
        """Move the cursor back to the domain that was selected before a reload."""
        if not previous:
            return
        table = self.query_one("#filing-table", DataTable)
        for index, row in enumerate(self.rows):
            if self._identity(row) == previous:
                table.move_cursor(row=index)
                return

    def _viewportRestore(self, scrollY: float) -> None:
        """Keep the selected row at the same visible position after a rebuild."""
        table = self.query_one("#filing-table", DataTable)
        table.scroll_y = scrollY
        self.call_after_refresh(lambda: setattr(table, "scroll_y", scrollY))

    def _destinationsClip(self) -> None:
        """Ellipsize Destination cells to the fitted column. Leave the editor alone."""
        width = self._widths.get("destination")
        if width is None:
            return
        table = self.query_one("#filing-table", DataTable)
        for index, row in enumerate(self.rows):
            if index >= table.row_count:
                return
            table.update_cell_at(
                Coordinate(index, _DESTINATION_COLUMN),
                Text(_textClip(str(row.get("canonical", "")), width)),
                update_width=False,
            )


## editor


class FilingEditor(Widget):
    """Compact destination editor for the selected filing domain."""

    BINDINGS = [
        Binding("alt+i", "disposition_ignore", "Ignore", show=False),
        Binding("alt+j", "disposition_junk", "Junk", show=False),
        Binding("alt+f", "disposition_file", "File", show=False),
        Binding("alt+s", "sender_edit", "Sender", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        """Start with no domain selected."""
        super().__init__(**kwargs)
        self._row: dict | None = None
        self._rows: list[dict] = []
        self._disposition = "file"
        self._shownChoice = ("", "", "")

    def compose(self) -> ComposeResult:
        """Rows for the choice, with exceptional fields hidden until needed."""
        yield Static(
            "Selected: choose a domain",
            id="filing-heading",
            classes="heading",
            markup=False,
        )
        with HorizontalGroup(id="filing-action-row"):
            yield Static("Action", classes="filing-label filing-lead")
            yield Static("Choose", id="filing-disposition", classes="filing-value")
        with HorizontalGroup(id="filing-parent-row"):
            yield Static("Parent", classes="filing-label filing-lead")
            yield Input(
                placeholder="Choose or type parent",
                id="filing-parent",
                compact=True,
                classes="filing-field filing-parent-field",
            )
            yield Select([], prompt="▼", id="filing-parent-options", compact=True)
        with HorizontalGroup(id="filing-folder-row"):
            yield Static("Folder", classes="filing-label filing-lead")
            yield Input(
                placeholder="Folder",
                id="filing-child",
                compact=True,
                classes="filing-field filing-folder-field",
            )
        with HorizontalGroup(id="filing-domain-row") as domainRow:
            domainRow.display = False
            yield Static("Organisation domain", classes="filing-label filing-lead")
            yield Input(
                placeholder="example.co.uk",
                id="filing-domain",
                compact=True,
                classes="filing-field",
            )
        with HorizontalGroup(id="filing-status-row"):
            yield Static(
                "i Ignore · j Junk · f File · s Sender",
                id="filing-shortcuts",
                classes="filing-label",
                markup=False,
            )
            yield Static(
                "",
                id="filing-row-status",
                classes="filing-value",
                markup=False,
            )
        with HorizontalGroup(id="filing-sender-row") as senderRow:
            senderRow.display = False
            yield Static("Sender", classes="filing-label filing-lead")
            yield Input(
                placeholder="Exact sender",
                id="filing-sender",
                compact=True,
                classes="filing-field",
            )
        yield Static("", id="filing-status", markup=False)

    def rowShow(self, row: dict | None, plan: dict) -> None:
        """Show the selected domain. Hide exceptional fields again."""
        if not self.query("#filing-parent"):
            return
        self._row = row
        self._rows = [row] if row else []
        self._senderHide()
        domainInput = self.query_one("#filing-domain", Input)
        domainInput.value = ""
        heading = self.query_one("#filing-heading", Static)
        status = self.query_one("#filing-row-status", Static)
        status.set_class(bool(row and _rowNeedsAction(row)), "warning")
        status.set_class(bool(row and _rowNeedsAction(row)), "action-needed")
        self.query_one("#filing-status", Static).update("")
        if not row:
            heading.update("Selected: choose a domain")
            self._actionShow("Choose")
            status.update("")
            self.query_one("#filing-domain-row").display = False
            self.query_one("#filing-child", Input).value = ""
            self.query_one("#filing-parent", Input).value = ""
            self._fileFieldsShow(True)
            self._shownChoice = self._choiceValues()
            return
        action = _rowAction(row)
        if action == "Choose":
            self._disposition = "file"
            self._actionShow("Choose")
            self._fileFieldsShow(True)
        else:
            self.dispositionSet(action.lower())
        heading.update(_headingText(row))
        status.update(_rowStatus(row))
        uncertain = bool(row.get("domainUncertain"))
        domainRow = self.query_one("#filing-domain-row")
        domainRow.display = uncertain
        if uncertain:
            domainInput.placeholder = str(row.get("domain") or "example.co.uk")
        chooser = self.query_one("#filing-parent-options", Select)
        options = _parentOptions(str(row.get("mailbox") or ""), plan)
        chooser.set_options(options)
        parent = row.get("parent")
        legal = {value for _prompt, value in options}
        with chooser.prevent(Select.Changed):
            chooser.value = (
                parent if isinstance(parent, str) and parent in legal else Select.NULL
            )
        parentInput = self.query_one("#filing-parent", Input)
        childInput = self.query_one("#filing-child", Input)
        parentInput.placeholder = "Choose or type parent"
        childInput.placeholder = "Folder"
        parentInput.value = str(parent or "")
        childInput.value = row.get("folder") or row.get("suggestion") or ""
        self._shownChoice = self._choiceValues()

    def rowsShow(self, rows: list[dict], plan: dict) -> None:
        """Show a desktop-style multi-selection for one bulk filing destination."""
        if len(rows) <= 1:
            self.rowShow(rows[0] if rows else None, plan)
            return
        self._rows = list(rows)
        self._row = rows[0]
        self._senderHide()
        self._disposition = "file"
        self._actionShow("File")
        self._fileFieldsShow(True)
        self.query_one("#filing-domain-row").display = False
        self.query_one("#filing-domain", Input).value = ""
        total = sum(int(row.get("inboxCount") or 0) for row in rows)
        self.query_one("#filing-heading", Static).update(
            f"Selected: {len(rows)} domains · {total} messages"
        )
        status = self.query_one("#filing-row-status", Static)
        status.set_class(False, "warning")
        status.set_class(False, "action-needed")
        status.update(f"Apply one destination to {len(rows)} selected domains")
        self.query_one("#filing-status", Static).update("")
        options = _parentOptionsMany(rows, plan)
        chooser = self.query_one("#filing-parent-options", Select)
        chooser.set_options(options)
        parents = {str(row.get("parent") or "") for row in rows}
        folders = {str(row.get("folder") or "") for row in rows}
        parent = next(iter(parents)) if len(parents) == 1 else ""
        child = next(iter(folders)) if len(folders) == 1 else ""
        legal = {value for _prompt, value in options}
        with chooser.prevent(Select.Changed):
            chooser.value = parent if parent and parent in legal else Select.NULL
        parentInput = self.query_one("#filing-parent", Input)
        childInput = self.query_one("#filing-child", Input)
        parentInput.placeholder = "Mixed parents" if len(parents) > 1 else "Choose or type parent"
        childInput.placeholder = "Mixed folders" if len(folders) > 1 else "Folder"
        parentInput.value = parent
        childInput.value = child
        self._shownChoice = self._choiceValues()

    def action_disposition_ignore(self) -> None:
        """Choose Ignore for an editor save, including a sender override."""
        self.dispositionSet("ignore")

    def action_disposition_junk(self) -> None:
        """Choose Junk for an editor save, including a sender override."""
        self.dispositionSet("junk")

    def action_disposition_file(self) -> None:
        """Choose File for an editor save."""
        self.dispositionSet("file")

    def dispositionSet(self, disposition: str) -> None:
        """Show a disposition without saving or changing mailbox state."""
        if disposition not in ("file", "ignore", "junk"):
            raise ValueError("Invalid filing disposition")
        self._disposition = disposition
        self._actionShow(disposition.title())
        self._fileFieldsShow(disposition == "file")

    def dispositionClear(self) -> None:
        """Reset selected saved Ignore/Junk domain decisions back to Choose."""
        targets = self._view().selectedRows() or ([self._row] if self._row else [])
        if not targets:
            return
        path = filing.filingPath()
        rules = filing.filingRulesLoad(path)
        changed = False
        for row in targets:
            entry = rules.get("mailboxes", {}).get(row["mailbox"], {})
            host = str(row.get("domain") or "").strip().lower().rstrip(".")
            domain = entry.get("clarifications", {}).get(host, host)
            decision = entry.get("domains", {}).get(domain)
            if isinstance(decision, dict) and decision.get("disposition") in (
                "ignore",
                "junk",
            ):
                entry["domains"].pop(domain, None)
                changed = True
        if changed:
            filing._filingWrite(rules, path)
            self._view().planRecompute()
        self._disposition = "file"
        self._actionShow("Choose")
        self._fileFieldsShow(True)
        self._status("Choose a filing destination.")

    def _actionShow(self, action: str) -> None:
        """Update the selected action without duplicating shortcut hints."""
        self.query_one("#filing-disposition", Static).update(action)

    def _fileFieldsShow(self, visible: bool) -> None:
        """Show destination fields only for File or an unresolved choice."""
        self.query_one("#filing-parent-row").display = visible
        self.query_one("#filing-folder-row").display = visible

    @on(Select.Changed, "#filing-parent-options")
    def parentChanged(self, event: Select.Changed) -> None:
        """Apply a dropdown choice through the editable parent field."""
        event.stop()
        if isinstance(event.value, str):
            self.query_one("#filing-parent", Input).value = event.value
            self._choiceSave()

    @on(Input.Submitted)
    def fieldSubmitted(self, event: Input.Submitted) -> None:
        """Commit an edit with Enter; Folder returns focus to the selected row."""
        if event.input.id in ("filing-parent", "filing-child", "filing-domain"):
            event.stop()
            self._ruleSave("domain")
            if event.input.id == "filing-child":
                self._view().query_one("#filing-table", DataTable).focus()
        elif event.input.id == "filing-sender":
            event.stop()
            self._ruleSave("sender")

    @on(DescendantBlur)
    def fieldBlurred(self, event: DescendantBlur) -> None:
        """Commit a completed destination edit when focus leaves its field."""
        if event.widget.id in ("filing-parent", "filing-child", "filing-domain"):
            self._choiceSave()

    def _choiceValues(self) -> tuple[str, str, str]:
        """Read editable values to detect user changes."""
        return tuple(
            self.query_one(f"#filing-{name}", Input).value
            for name in ("parent", "child", "domain")
        )

    def _choiceSave(self) -> None:
        """Save changed choices; leave partial entries for correction."""
        if not self._row or self._choiceValues() == self._shownChoice:
            return
        self._ruleSave("domain")

    def action_sender_edit(self) -> None:
        """Reveal and focus a sender field; Enter saves the override."""
        if len(self._view().selectedRows()) > 1:
            self._status("Sender override requires one selected domain.")
            return
        if not self._row:
            self._status("Select a filing domain first.")
            return
        self.query_one("#filing-sender-row").display = True
        self.query_one("#filing-sender", Input).focus()

    def _ruleSave(self, kind: str) -> None:
        """Persist one rule or one bulk domain decision and refresh the plan."""
        row = self._row
        if not row:
            self._status("Select a filing domain first.")
            return
        targets = self._view().selectedRows() or [row]
        try:
            if kind == "sender" and len(targets) > 1:
                raise ValueError("Sender override requires one selected domain")
            if len(targets) > 1 and any(target.get("domainUncertain") for target in targets):
                raise ValueError("Resolve uncertain organisation domains individually first")
            disposition = self._disposition
            if disposition in ("ignore", "junk"):
                for target in targets:
                    identity = (
                        self._confirmedDomain(target)
                        if len(targets) == 1 and kind == "domain"
                        else (
                            target["domain"]
                            if kind == "domain"
                            else senderNormalize(
                                self.query_one("#filing-sender", Input).value
                            )
                        )
                    )
                    rules = filing.filingRulesLoad(filing.filingPath())
                    if kind == "sender" and (
                        not identity
                        or not filing.filingDomainMatch(
                            identity,
                            target["domain"],
                            rules,
                            target["mailbox"],
                        )
                    ):
                        raise ValueError("Enter a sender in the selected domain")
                    filing.filingDispositionSet(
                        target["mailbox"],
                        "domains" if kind == "domain" else "senders",
                        identity,
                        disposition,
                        filing.filingPath(),
                    )
                self._view().planRecompute()
                suffix = f" for {len(targets)} domains" if len(targets) > 1 else ""
                self._status(f"Saved: {disposition.title()}{suffix}")
                return
            if len(targets) > 1:
                parent = filing.filingNameNormalize(
                    self.query_one("#filing-parent", Input).value
                )
                child = filing.filingNameNormalize(
                    self.query_one("#filing-child", Input).value
                )
                plan = self._view()._plan()
                for target in targets:
                    discovered = set(
                        plan.get("parents", {}).get(target["mailbox"], [])
                    )
                    filing.filingDomainSet(
                        target["mailbox"],
                        target["domain"],
                        parent,
                        child,
                        parent not in discovered,
                        filing.filingPath(),
                    )
                self._view().planRecompute()
                self._status(f"Saved {len(targets)} domains: {parent}/{child}")
                return
            parent, child, proposed = self._choiceRead(row)
            if kind == "domain":
                self._domainStore(row, parent, child, proposed)
            else:
                self._senderStore(row, parent, child, proposed)
            self._view().planRecompute()
        except (OSError, ValueError) as error:
            self._status(str(error))
            return
        self._status(f"Saved: {parent}/{child}")

    def _choiceRead(self, row: dict) -> tuple[str, str, bool]:
        """Read the editable destination, proposing unknown parents."""
        plan = self._view()._plan()
        discovered = set(plan.get("parents", {}).get(row["mailbox"], []))
        parent = filing.filingNameNormalize(
            self.query_one("#filing-parent", Input).value
        )
        child = filing.filingNameNormalize(self.query_one("#filing-child", Input).value)
        return parent, child, parent not in discovered

    def _domainStore(self, row: dict, parent: str, child: str, proposed: bool) -> str:
        """Save a domain rule, clarifying an uncertain host when one was typed."""
        domain = self._confirmedDomain(row)
        filing.filingDomainSet(
            row["mailbox"], domain, parent, child, proposed, filing.filingPath()
        )
        return domain

    def _confirmedDomain(self, row: dict) -> str:
        """Use a typed organisation domain when the shown host is uncertain."""
        typed = self.query_one("#filing-domain", Input).value.strip()
        if not typed:
            return row["domain"]
        if not row.get("domainUncertain"):
            raise ValueError("This domain is already determined")
        saved = filing.filingDomainClarify(
            row["mailbox"], row["domain"], typed, filing.filingPath()
        )
        host = row["domain"].strip().lower().rstrip(".")
        return saved["mailboxes"][row["mailbox"]]["clarifications"][host]

    def _senderStore(self, row: dict, parent: str, child: str, proposed: bool) -> str:
        """Save an exact sender override when the address belongs to this domain."""
        sender = senderNormalize(self.query_one("#filing-sender", Input).value)
        if not sender:
            raise ValueError("Enter an exact sender address")
        rules = filing.filingRulesLoad(filing.filingPath())
        if not filing.filingDomainMatch(sender, row["domain"], rules, row["mailbox"]):
            raise ValueError(f"Sender is not in {row['domain']}")
        filing.filingSenderSet(
            row["mailbox"], sender, parent, child, proposed, filing.filingPath()
        )
        return sender

    def _view(self) -> "FilingView":
        """Return the filing workspace that owns this editor."""
        view = self.parent
        while view is not None and not isinstance(view, FilingView):
            view = view.parent
        if not isinstance(view, FilingView):
            raise RuntimeError("Filing editor is not inside a filing view")
        return view

    def _senderHide(self) -> None:
        """Hide the sender override and clear it when the domain changes."""
        self.query_one("#filing-sender-row").display = False
        self.query_one("#filing-sender", Input).value = ""

    def _status(self, message: str) -> None:
        """Show the result of the last filing action."""
        self.query_one("#filing-status", Static).update(message)


## columns


def _columnSpecs() -> tuple[tuple[str, str, int], ...]:
    """Return the filing columns in display order, with their initial widths."""
    return (
        ("domain", "Domain", 24),
        ("archive", "Archive", 12),
        ("inbox", "#", 6),
        ("parent", "Parent", 14),
        ("folder", "Folder", 16),
        ("destination", "Destination", 16),
        ("action", "Action", 10),
        ("status", "Status", 20),
    )


def _columnWidths(available: int, padding: int) -> dict[str, int]:
    """Fit content widths into the table. Domain keeps most of the spare space."""
    fixed = {
        "archive": 12,
        "inbox": 6,
        "parent": 14,
        "folder": 16,
        "action": 10,
        "status": 20,
    }
    floors = {
        "archive": 8,
        "inbox": 3,
        "parent": 8,
        "folder": 8,
        "action": 6,
        "status": 8,
    }
    domainMin = 12
    destinationMin = 8
    pad = padding * 2
    columnCount = len(fixed) + 2

    def used(domain: int, destination: int) -> int:
        return sum(fixed.values()) + domain + destination + pad * columnCount

    for key in ("status", "folder", "parent", "archive", "action", "inbox"):
        while fixed[key] > floors[key] and used(domainMin, destinationMin) > available:
            fixed[key] -= 1
    leftover = available - used(0, 0)
    if leftover < 1:
        fixed["domain"] = 1
        fixed["destination"] = 1
        return fixed
    domain = int(leftover * 0.65)
    destination = leftover - domain
    if destination < destinationMin:
        destination = min(destinationMin, leftover)
        domain = leftover - destination
    if domain < domainMin and leftover >= domainMin + destinationMin:
        domain = domainMin
        destination = leftover - domain
    fixed["domain"] = max(domain, 1)
    fixed["destination"] = max(destination, 1)
    return fixed


def _domainCell(row: dict, marked: bool) -> Text:
    """Render a visible multi-selection mark without adding another column."""
    prefix = "✓ " if marked else "  "
    style = "bold #5bd1b9" if marked else ""
    return Text(prefix + str(row.get("domain", "")), style=style)


def _tableCells(row: dict, destinationWidth: int, marked: bool = False) -> tuple:
    """Return one table row, with Action distinct from destination status."""
    action = _rowAction(row)
    status = _rowStatus(row)
    return (
        _domainCell(row, marked),
        Text(str(row.get("archive", ""))),
        Text(str(row.get("inboxCount", ""))),
        Text(str(row.get("parent", ""))),
        Text(str(row.get("folder", ""))),
        Text(_textClip(str(row.get("canonical", "")), destinationWidth)),
        Text(action, style="bold #f0c76a" if action == "Choose" else ""),
        Text(status),
    )


def _textClip(value: str, width: int) -> str:
    """Clip one cell and mark the cut with an ellipsis."""
    if width <= 0:
        return ""
    if len(value) <= width:
        return value
    if width == 1:
        return "…"
    return value[: width - 1] + "…"


## text


def _actionText(rows: list[dict]) -> str:
    """Explain the next available user action without implying execution exists."""
    choices = sum(_rowNeedsChoice(row) for row in rows)
    proposed = sum(_rowNeedsAction(row) and not _rowNeedsChoice(row) for row in rows)
    prompts = []
    if choices:
        prompts.append(
            f"{choices} domains need an action · enter a destination to File · i Ignore · j Junk"
        )
    if proposed:
        prompts.append(f"review proposed folders for {proposed} domains")
    return "⚠ ACTION NEEDED: " + "; ".join(prompts) + "." if prompts else ""


def _rowAction(row: dict) -> str:
    """Return the user-facing action independently from destination status."""
    disposition = str(row.get("disposition") or "").lower()
    if disposition == "ignore":
        return "Ignore"
    if disposition == "junk":
        return "Junk"
    if _rowNeedsChoice(row):
        return "Choose"
    if row.get("canonical") or (row.get("parent") and row.get("folder")):
        return "File"
    return "Choose"


def _rowStatus(row: dict) -> str:
    """Return only destination state; actions live in their own column."""
    status = str(row.get("status") or "")
    if status in ("Needs choice", "Ignore", "Junk"):
        return ""
    return status


def _rowNeedsAction(row: dict) -> bool:
    """Identify domain decisions or proposed folders requiring user review."""
    return _rowNeedsChoice(row) or (
        str(row.get("status", "")).startswith("Proposed")
        and row.get("decisionSource") not in ("domain", "sender")
    )


def _rowNeedsChoice(row: dict) -> bool:
    """A saved complete rule resolves a choice even for a proposed folder."""
    return row.get("status") == "Needs choice" or (
        bool(row.get("domainUncertain"))
        and row.get("decisionSource") not in ("domain", "sender")
    )


def _summaryText() -> str:
    """Return the one-line filing introduction."""
    return "Read mail may be filed. No folders or mail are changed in this phase."


def _headingText(row: dict) -> str:
    """Return the selected-domain heading, with a pluralised message count."""
    count = int(row.get("inboxCount") or 0)
    noun = "message" if count == 1 else "messages"
    domain = row.get("domain", "")
    archive = row.get("archive", "")
    return f"Selected: {domain} · {archive} · {count} {noun}"


def _overrideText(plan: dict) -> str:
    """Return the sender-override line, or nothing when there are none."""
    lines = [
        f'{item["sender"]} -> {item.get("canonical") or item.get("disposition", "file").title()} ({item["mailbox"]})'
        for item in plan.get("senderOverrides", [])
    ]
    if not lines:
        return ""
    return "Sender overrides: " + "; ".join(lines)


def _parentOptions(mailbox: str, plan: dict) -> list[tuple[str, str]]:
    """Return discovered and proposed parents for the dropdown."""
    discovered = list(plan.get("parents", {}).get(mailbox, []))
    proposed = [
        name
        for name in plan.get("proposedParents", {}).get(mailbox, [])
        if name not in discovered
    ]
    options = [(name, name) for name in discovered]
    options.extend((f"{name} (proposed)", name) for name in proposed)
    return options


def _parentOptionsMany(rows: list[dict], plan: dict) -> list[tuple[str, str]]:
    """Return the union of parent choices represented by selected mailboxes."""
    found: dict[str, str] = {}
    for mailbox in dict.fromkeys(str(row.get("mailbox") or "") for row in rows):
        for prompt, value in _parentOptions(mailbox, plan):
            current = found.get(value)
            if current is None or "(proposed)" not in prompt:
                found[value] = prompt
    return [(found[value], value) for value in sorted(found, key=str.casefold)]
