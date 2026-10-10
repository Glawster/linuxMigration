"""Compact Inbox filing workspace.

The table lists organisation domains. The editor records rules only:
it does not create folders or move mail.
"""

from pathlib import Path

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.containers import HorizontalGroup
from textual.coordinate import Coordinate
from textual.events import Mount, Resize
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Select, Static
from textual.widgets.data_table import ColumnKey

import mailAgent.filing as filing
from mailAgent.actionGuidance import ActionNeeded
from mailAgent.senderAddress import senderNormalize

# Loaded as application CSS. Widget DEFAULT_CSS cannot override the shared sheet.
FILING_CSS = Path(__file__).with_suffix(".tcss").read_text(encoding="utf-8")
_DESTINATION_COLUMN = 5


## view


class FilingView(Widget):
    """Domain table with a compact rule editor beneath it."""

    def __init__(self, snapshot: dict, issue: str | None = None) -> None:
        """Keep the shared snapshot. Saves write rules, then replace its plan."""
        super().__init__()
        self.snapshot = snapshot
        self.issue = issue
        plan = snapshot.get("filingPlan") or {}
        self.rows: list[dict] = list(plan.get("rows") or [])
        self._widths: dict[str, int] = {}
        self._columnKeys: dict[str, ColumnKey] = {}
        self._fitting = False

    def compose(self) -> ComposeResult:
        """One summary line, a scrolling table, then the editor."""
        plan = self._plan()
        yield ActionNeeded(
            _actionText(self.rows) or _summaryText(),
            id="filing-summary",
            classes="warning action-needed" if _actionText(self.rows) else "",
            markup=False,
        )
        if self.issue:
            yield Static(self.issue, id="filing-issue", markup=False)
        table = DataTable(id="filing-table", cursor_type="row")
        for key, label, width in _columnSpecs():
            self._columnKeys[key] = table.add_column(label, width=width, key=key)
        for row in self.rows:
            table.add_row(*_tableCells(row, 16))
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
            else (
                "#filing-parent"
                if row.get("status") == "Needs choice"
                else "#filing-child"
            )
        )
        self.query_one(target).focus()

    def planShow(self) -> None:
        """Reload the table from the snapshot, keeping the selected domain."""
        previous = self._selectedIdentity()
        plan = self._plan()
        self.rows = list(plan.get("rows") or [])
        table = self.query_one("#filing-table", DataTable)
        table.clear(columns=False)
        destinationWidth = self._widths.get("destination", 16)
        for row in self.rows:
            table.add_row(*_tableCells(row, destinationWidth))
        self._cursorRestore(previous)
        action = self.query_one("#filing-summary", Static)
        action.update(_actionText(self.rows) or _summaryText())
        action.set_class(bool(_actionText(self.rows)), "warning")
        action.set_class(bool(_actionText(self.rows)), "action-needed")
        self._overridesShow(plan)
        empty = self.query_one("#filing-empty", Static)
        empty.update("" if self.rows else "No Inbox domains to file")
        empty.display = not self.rows
        self._editorSync()
        self.columnsFit()

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
            with table.prevent(DataTable.RowHighlighted):
                table.clear(columns=True)
                for name, label, _width in _columnSpecs():
                    self._columnKeys[name] = table.add_column(
                        label, width=widths[name], key=name
                    )
                for row in self.rows:
                    table.add_row(*_tableCells(row, widths["destination"]))
                self._cursorRestore(previous)
            self._destinationsClip()
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

    @on(DataTable.RowHighlighted, "#filing-table")
    def rowHighlighted(self, event: DataTable.RowHighlighted) -> None:
        """Keep the editor on the highlighted domain."""
        event.stop()
        if not self.query("#filing-editor"):
            return
        row = None
        if 0 <= event.cursor_row < len(self.rows):
            row = self.rows[event.cursor_row]
        self.query_one(FilingEditor).rowShow(row, self._plan())

    def _plan(self) -> dict:
        """Return the filing plan currently stored on the snapshot."""
        return self.snapshot.get("filingPlan") or {}

    def _editorSync(self) -> None:
        """Show whichever domain the table cursor is on."""
        if not self.query("#filing-editor"):
            return
        self.query_one(FilingEditor).rowShow(self._selectedRow(), self._plan())

    def _overridesShow(self, plan: dict) -> None:
        """Show exact sender overrides only when at least one exists."""
        widget = self.query_one("#filing-overrides", Static)
        text = _overrideText(plan)
        widget.update(text)
        widget.display = bool(text)

    def _selectedRow(self) -> dict | None:
        """Return the domain under the cursor, or the first domain."""
        if not self.rows or not self.query("#filing-table"):
            return None
        table = self.query_one("#filing-table", DataTable)
        row = table.cursor_row
        if not isinstance(row, int) or row < 0 or row >= len(self.rows):
            row = 0
        return self.rows[row]

    def _selectedIdentity(self) -> tuple[str, str] | None:
        """Return the selected mailbox and domain, if a row is selected."""
        row = self._selectedRow()
        if not row:
            return None
        return row["mailbox"], row["domain"]

    def _cursorRestore(self, previous: tuple[str, str] | None) -> None:
        """Move the cursor back to the domain that was selected before a reload."""
        if not previous:
            return
        table = self.query_one("#filing-table", DataTable)
        for index, row in enumerate(self.rows):
            if (row["mailbox"], row["domain"]) == previous:
                table.move_cursor(row=index)
                return

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

    def __init__(self, **kwargs) -> None:
        """Start with no domain selected."""
        super().__init__(**kwargs)
        self._row: dict | None = None

    def compose(self) -> ComposeResult:
        """Rows for the choice, with the rare fields hidden until needed."""
        yield Static(
            "Filing: select a domain",
            id="filing-heading",
            classes="heading",
            markup=False,
        )
        with HorizontalGroup(id="filing-choice-row"):
            yield Static("Parent", classes="filing-label filing-lead")
            yield Select(
                [("Add parent...", "__add__")],
                prompt="Parent",
                id="filing-parent",
                compact=True,
                classes="filing-field",
            )
            yield Static("Folder", classes="filing-label")
            yield Input(
                placeholder="Folder",
                id="filing-child",
                compact=True,
                classes="filing-field",
            )
        with HorizontalGroup(id="filing-parent-name-row") as parentName:
            parentName.display = False
            yield Static("New parent", classes="filing-label filing-lead")
            yield Input(
                placeholder="New parent name",
                id="filing-parent-name",
                compact=True,
                classes="filing-field",
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
            yield Select(
                [("File", "file"), ("Ignore", "ignore"), ("Junk", "junk")],
                value="file",
                allow_blank=False,
                id="filing-disposition",
                compact=True,
                classes="filing-lead",
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
        with HorizontalGroup(id="filing-actions"):
            yield Button(
                "Add parent",
                id="filing-add-parent",
                compact=True,
                classes="filing-action",
            )
            yield Button(
                "Save domain",
                id="filing-save-domain",
                compact=True,
                classes="filing-action",
            )
            yield Button(
                "Sender override",
                id="filing-save-sender",
                compact=True,
                classes="filing-action",
            )
        yield Static("", id="filing-status", markup=False)

    def rowShow(self, row: dict | None, plan: dict) -> None:
        """Show the selected domain. Hide the rare fields again."""
        if not self.query("#filing-parent"):
            return
        self._row = row
        self._senderHide()
        self._parentNameHide()
        domainInput = self.query_one("#filing-domain", Input)
        domainInput.value = ""
        heading = self.query_one("#filing-heading", Static)
        status = self.query_one("#filing-row-status", Static)
        status.set_class(bool(row and _rowNeedsAction(row)), "warning")
        status.set_class(bool(row and _rowNeedsAction(row)), "action-needed")
        if not row:
            heading.update("Filing: select a domain")
            status.update("")
            self.query_one("#filing-domain-row").display = False
            self.query_one("#filing-child", Input).value = ""
            return
        self.query_one("#filing-disposition", Select).value = row.get(
            "disposition", "file"
        )
        heading.update(_headingText(row))
        status.update(str(row.get("status") or ""))
        uncertain = bool(row.get("domainUncertain"))
        domainRow = self.query_one("#filing-domain-row")
        domainRow.display = uncertain
        if uncertain:
            domainInput.placeholder = str(row.get("domain") or "example.co.uk")
        chooser = self.query_one("#filing-parent", Select)
        options = _parentOptions(str(row.get("mailbox") or ""), plan)
        chooser.set_options(options)
        parent = row.get("parent")
        legal = {value for _prompt, value in options}
        if isinstance(parent, str) and parent in legal:
            chooser.value = parent
        self.query_one("#filing-child", Input).value = (
            row.get("folder") or row.get("suggestion") or ""
        )

    @on(Select.Changed, "#filing-disposition")
    def dispositionChanged(self, event: Select.Changed) -> None:
        """Only File needs a parent and folder."""
        event.stop()
        isFile = event.value == "file"
        self.query_one("#filing-choice-row").display = isFile
        self.query_one("#filing-add-parent", Button).disabled = not isFile
        if not isFile:
            self._parentNameHide()

    @on(Select.Changed, "#filing-parent")
    def parentChanged(self, event: Select.Changed) -> None:
        """Ask for a new parent name only when Add parent... is chosen."""
        event.stop()
        show = event.value == "__add__"
        self.query_one("#filing-parent-name-row").display = show
        if show:
            self.query_one("#filing-parent-name", Input).focus()

    @on(Button.Pressed, "#filing-add-parent")
    def parentAdd(self, event: Button.Pressed) -> None:
        """Record a proposed parent. A typed name is saved even while hidden."""
        event.stop()
        row = self._row
        if not row:
            self._status("Select a filing domain first.")
            return
        nameInput = self.query_one("#filing-parent-name", Input)
        nameRow = self.query_one("#filing-parent-name-row")
        if not nameInput.value.strip() and not nameRow.display:
            nameRow.display = True
            nameInput.focus()
            return
        try:
            parent = filing.filingNameNormalize(nameInput.value)
            discovered = set(
                self._view()._plan().get("parents", {}).get(row["mailbox"], [])
            )
            if parent in discovered:
                self._status(f"{parent} already exists.")
                return
            filing.filingParentAdd(row["mailbox"], parent, filing.filingPath())
            self._view().planRecompute()
        except (OSError, ValueError) as error:
            self._status(str(error))
            return
        self._status(f"Proposed parent {parent}. No folder was created.")

    @on(Button.Pressed, "#filing-save-domain")
    def domainSave(self, event: Button.Pressed) -> None:
        """Persist the domain rule for the selected row. Mail is not moved."""
        event.stop()
        self._ruleSave("domain")

    @on(Button.Pressed, "#filing-save-sender")
    def senderSave(self, event: Button.Pressed) -> None:
        """Reveal the sender field, then save an exact override on the next press."""
        event.stop()
        if not self._row:
            self._status("Select a filing domain first.")
            return
        senderRow = self.query_one("#filing-sender-row")
        if not senderRow.display:
            senderRow.display = True
            self.query_one("#filing-sender", Input).focus()
            return
        self._ruleSave("sender")

    def _ruleSave(self, kind: str) -> None:
        """Persist one domain rule or sender override and refresh the plan."""
        row = self._row
        if not row:
            self._status("Select a filing domain first.")
            return
        try:
            disposition = self.query_one("#filing-disposition", Select).value
            if disposition in ("ignore", "junk"):
                identity = (
                    self._confirmedDomain(row)
                    if kind == "domain"
                    else senderNormalize(self.query_one("#filing-sender", Input).value)
                )
                rules = filing.filingRulesLoad(filing.filingPath())
                if kind == "sender" and (
                    not identity
                    or not filing.filingDomainMatch(
                        identity, row["domain"], rules, row["mailbox"]
                    )
                ):
                    raise ValueError("Enter a sender in the selected domain")
                filing.filingDispositionSet(
                    row["mailbox"],
                    "domains" if kind == "domain" else "senders",
                    identity,
                    disposition,
                    filing.filingPath(),
                )
                self._view().planRecompute()
                self._status(
                    f"Saved {identity}: {disposition.title()}. Mail was not changed."
                )
                return
            parent, child, proposed = self._choiceRead(row)
            saved = (
                self._domainStore(row, parent, child, proposed)
                if kind == "domain"
                else self._senderStore(row, parent, child, proposed)
            )
            self._view().planRecompute()
        except (OSError, ValueError) as error:
            self._status(str(error))
            return
        self._status(f"Saved {saved} -> {parent}/{child}. Mail was not changed.")

    def _choiceRead(self, row: dict) -> tuple[str, str, bool]:
        """Read the parent and folder. Add parent... uses the name field."""
        plan = self._view()._plan()
        discovered = set(plan.get("parents", {}).get(row["mailbox"], []))
        selection = self.query_one("#filing-parent", Select).value
        if not isinstance(selection, str) or selection == "__add__":
            parent = filing.filingNameNormalize(
                self.query_one("#filing-parent-name", Input).value
            )
        else:
            parent = filing.filingNameNormalize(selection)
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

    def _parentNameHide(self) -> None:
        """Hide the new-parent field and drop any name from another domain."""
        self.query_one("#filing-parent-name-row").display = False
        self.query_one("#filing-parent-name", Input).value = ""

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
        ("status", "Status", 22),
    )


def _columnWidths(available: int, padding: int) -> dict[str, int]:
    """Fit content widths into the table. Domain keeps most of the spare space."""
    fixed = {
        "archive": 12,
        "inbox": 6,
        "parent": 14,
        "folder": 16,
        "status": 22,
    }
    floors = {
        "archive": 8,
        "inbox": 3,
        "parent": 8,
        "folder": 8,
        "status": 8,
    }
    domainMin = 12
    destinationMin = 8
    pad = padding * 2
    columnCount = len(fixed) + 2

    def used(domain: int, destination: int) -> int:
        return sum(fixed.values()) + domain + destination + pad * columnCount

    for key in ("status", "folder", "parent", "archive", "inbox"):
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


def _tableCells(row: dict, destinationWidth: int) -> tuple:
    """Return one table row, with Destination clipped to its column."""
    return (
        Text(str(row.get("domain", ""))),
        Text(str(row.get("archive", ""))),
        Text(str(row.get("inboxCount", ""))),
        Text(str(row.get("parent", ""))),
        Text(str(row.get("folder", ""))),
        Text(_textClip(str(row.get("canonical", "")), destinationWidth)),
        Text(
            str(row.get("status", "")),
            style="bold #f0c76a" if _rowNeedsAction(row) else "",
        ),
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
            f"{choices} domains need a choice: select a row, then Save domain"
        )
    if proposed:
        prompts.append(f"review proposed folders for {proposed} domains")
    return "⚠ ACTION NEEDED: " + "; ".join(prompts) + "." if prompts else ""


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
    return f"Filing: {domain} · {archive} · {count} {noun}"


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
    """Return discovered parents, proposed parents, and Add parent...."""
    discovered = list(plan.get("parents", {}).get(mailbox, []))
    proposed = [
        name
        for name in plan.get("proposedParents", {}).get(mailbox, [])
        if name not in discovered
    ]
    options = [(name, name) for name in discovered]
    options.extend((f"{name} (proposed)", name) for name in proposed)
    options.append(("Add parent...", "__add__"))
    return options
