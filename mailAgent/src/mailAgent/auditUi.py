"""Presentation only for the core audit and planning models."""

from pathlib import Path
from rich.text import Text
from textual.binding import Binding
from textual.app import App, ComposeResult
from textual.coordinate import Coordinate
from textual.containers import VerticalScroll
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from mailAgent.interest import interestIs, interestLoad, interestSet
from mailAgent.planSummary import planSummaryLines

## presentation


def auditAppBuild(snapshot: dict) -> App:
    """Construct the audit app for interactive use or headless validation."""
    try:
        interestData = interestLoad()
        interestIssue = None
    except (OSError, ValueError):
        interestData = {"schemaVersion": 1, "mailboxes": {}}
        interestIssue = "Interesting-sender preferences could not be loaded"
    senderRows = _interestRows(snapshot, interestData)

    class MailboxAudit(App):
        TITLE = "Mailbox Audit"
        BINDINGS = [
            ("q", "quit", "Quit"),
            Binding(
                "space",
                "toggle_interest",
                "Space to Toggle Sender of interest",
                show=False,
            ),
        ]

        def compose(self) -> ComposeResult:
            yield Header()
            yield Static(
                "Read-only audit · Migration execution disabled",
                id="safety",
                markup=False,
            )
            with TabbedContent():
                with TabPane("Folders", id="folders"):
                    yield from _foldersPane(snapshot)
                yield from _interestPane(senderRows, interestIssue)
                yield from _auditPanes(snapshot)
                yield from _planPane(snapshot.get("migrationPlan"))
            yield Footer()

        def action_toggle_interest(self) -> None:
            """Toggle the selected sender as interesting without changing mail."""
            table = self.query_one("#interest-table", DataTable)
            if self.focused is not table or not senderRows:
                return
            row = table.cursor_row
            if row < 0 or row >= len(senderRows):
                return
            entry = senderRows[row]
            interesting = not entry["interesting"]
            interestSet(entry["mailbox"], entry["sender"], interesting)
            entry["interesting"] = interesting
            table.update_cell_at(
                Coordinate(row, 0),
                Text("✓" if interesting else ""),
            )

        def on_input_changed(self, event: Input.Changed) -> None:
            """Filter grouped Proposed Moves without changing the stored plan."""
            if event.input.id != "proposal-filter":
                return
            plan = snapshot.get("migrationPlan")
            if not plan:
                return
            table = self.query_one("#proposal-table", DataTable)
            rows = _proposalRowsFiltered(plan, event.value)
            table.clear(columns=False)
            for row in rows:
                table.add_row(*(Text(str(cell)) for cell in row))
            self.query_one("#proposal-filter-status", Static).update(
                f"Showing {len(rows)} of {len(_proposalRows(plan))} grouped moves"
            )

        def on_button_pressed(self, event: Button.Pressed) -> None:
            """Handle planning refresh and explicit review decisions."""
            if event.button.id == "resolve-sender":
                self._senderResolutionSave(snapshot.get("migrationPlan"))
                return
            if event.button.id in ("run-planning", "refresh-planning"):
                self.exit("runPlanning")

        def _senderResolutionSave(self, plan: dict | None) -> None:
            if not plan:
                return
            table = self.query_one("#review-table", DataTable)
            chooser = self.query_one("#review-folder", Select)
            status = self.query_one("#review-resolution-status", Static)
            row = table.cursor_row
            if row < 0 or row >= len(plan["reviewQueue"]):
                status.update("Select a Review Queue row first.")
                return
            entry = plan["reviewQueue"][row]
            source = entry.get("source", {})
            sender = source.get("sender")
            targetMailbox = entry.get("targetMailbox")
            if not sender or not targetMailbox:
                status.update("This review item is not a sender-classification decision.")
                return
            selection = chooser.value
            if not isinstance(selection, tuple) or len(selection) != 2:
                status.update("Choose a canonical folder first.")
                return
            selectedMailbox, canonical = selection
            if selectedMailbox != targetMailbox:
                status.update(f"Choose a folder belonging to {targetMailbox}.")
                return
            from mailAgent.planResolution import senderResolutionSet

            senderResolutionSet(
                entry["mailbox"],
                sender,
                targetMailbox,
                canonical,
            )
            self.exit("runPlanning")

    return MailboxAudit()


def auditShow(snapshot: dict) -> str | None:
    """Display audit facts and return any requested follow-up workflow."""
    return auditAppBuild(snapshot).run()


def _interestPane(senderRows: list[dict], issue: str | None) -> ComposeResult:
    with TabPane("Inbox Digest", id="inboxInterest"):
        yield Static(
            "Select a sender row and press Space to toggle ✓ Sender of interest. "
            "Selected senders are candidates for the daily digest.",
            markup=False,
        )
        yield Static(
            "Space to Toggle Sender of interest",
            id="digest-footer",
            markup=False,
        )
        if issue:
            yield Static(issue, markup=False)
        table = DataTable(id="interest-table", cursor_type="row")
        table.add_columns(
            "Interesting", "Mailbox", "Sender", "Inbox messages", "Example subject"
        )
        for entry in senderRows:
            table.add_row(
                Text("✓" if entry["interesting"] else ""),
                Text(entry["mailbox"]),
                Text(entry["sender"]),
                Text(str(entry["count"])),
                Text(entry["subject"]),
            )
        yield table
        if not senderRows:
            yield Static("No Inbox sender headers available", markup=False)


def _interestRows(snapshot: dict, interestData: dict) -> list[dict]:
    grouped = {}
    for mailbox in snapshot["mailboxes"]:
        identity = mailbox["id"]
        for message in mailbox.get("inboxInventory", {}).get("messages", []):
            sender = message.get("sender")
            if not sender:
                continue
            key = (identity, sender)
            entry = grouped.setdefault(
                key,
                dict(
                    mailbox=identity,
                    sender=sender,
                    count=0,
                    subject="",
                    interesting=interestIs(interestData, identity, sender),
                ),
            )
            entry["count"] += 1
            if message.get("subject"):
                entry["subject"] = message["subject"]
    return sorted(
        grouped.values(),
        key=lambda entry: (
            not entry["interesting"],
            entry["mailbox"],
            entry["sender"],
        ),
    )


def _planPane(plan: dict | None) -> ComposeResult:
    """Always show Plan; expose planning detail as a second-level menu."""
    with TabPane("Plan", id="plan"):
        if plan is None:
            with VerticalScroll():
                yield Static(
                    "Planning has not been run for this session.",
                    id="plan-summary",
                    markup=False,
                )
                yield Button(
                    "Refresh Plan",
                    id="run-planning",
                    variant="primary",
                )
            return

        with TabbedContent(id="plan-menu"):
            with TabPane("Summary", id="planSummary"):
                with VerticalScroll():
                    generated = plan.get("generatedAt")
                    if generated:
                        yield Static(
                            "Stored plan from " + generated,
                            id="plan-generated",
                            markup=False,
                        )
                    yield Button(
                        "Refresh Plan",
                        id="refresh-planning",
                        variant="primary",
                    )
                    yield Static(
                        "\n".join(planSummaryLines(plan)),
                        id="plan-summary",
                        markup=False,
                    )
            yield from _planningPanes(plan)


def _planningPanes(plan: dict) -> ComposeResult:
    specifications = (
        (
            "Mapping",
            "mappings",
            "Canonical archive folders and their IMAP equivalents",
            ("Mailbox", "Archive folder", "IMAP folder", "Status"),
        ),
        (
            "Proposed Moves",
            "proposals",
            "Grouped for review; individual message proposals remain in the plan",
            ("From", "Sender", "#", "Year", "To", "Why"),
        ),
        (
            "Review Queue",
            "reviewQueue",
            "Items that still need a decision",
            ("Mailbox", "Folder / message", "Reason"),
        ),
        (
            "Role Boundaries",
            "excluded",
            "Mailboxes excluded from personal archive planning",
            ("Mailbox", "Role", "Policy"),
        ),
    )
    for title, key, label, columns in specifications:
        with TabPane(title, id=key):
            yield Static(label, markup=False)
            if key == "proposals":
                yield Input(
                    placeholder="Filter by source, sender, year, destination or reason",
                    id="proposal-filter",
                )
                yield Static(
                    f"Showing {len(_proposalRows(plan))} grouped moves",
                    id="proposal-filter-status",
                    markup=False,
                )
            table = DataTable(
                id=(
                    "review-table"
                    if key == "reviewQueue"
                    else "proposal-table" if key == "proposals" else None
                ),
                cursor_type="row" if key in ("reviewQueue", "proposals") else "cell",
            )
            table.add_columns(*columns)
            entries = (
                _proposalRows(plan)
                if key == "proposals"
                else [_planningRow(key, entry) for entry in plan[key]]
            )
            for row in entries:
                table.add_row(*(Text(str(cell)) for cell in row))
            yield table
            if key == "reviewQueue":
                options = [
                    (
                        f'{mapping["mailbox"]} — {mapping["canonical"]}',
                        (mapping["mailbox"], mapping["canonical"]),
                    )
                    for mapping in plan["mappings"]
                    if mapping.get("localSelectable")
                ]
                yield Static(
                    "For an unclassified sender, select its Review Queue row, "
                    "choose the canonical folder, then save. The decision applies "
                    "to that sender in the source mailbox.",
                    markup=False,
                )
                yield Select(
                    options,
                    prompt="Choose canonical folder",
                    id="review-folder",
                )
                yield Button(
                    "Use folder for selected sender",
                    id="resolve-sender",
                    variant="primary",
                )
                yield Static("", id="review-resolution-status", markup=False)
            if not plan[key]:
                yield Static("No entries", markup=False)


def _planningRow(key: str, entry: dict) -> tuple:
    if key == "mappings":
        status = entry.get(
            "issue", "Existing folder" if entry["imapExists"] else "Folder proposed"
        )
        return (
            entry["mailbox"],
            entry["canonical"],
            _folderDisplay(entry["imap"]) if entry["imap"] else "Unavailable",
            status,
        )
    if key == "proposals":
        return _proposalRow(entry, {})
    if key == "reviewQueue":
        source = entry.get("source", {})
        folder = _folderDisplay(source.get("folder", entry.get("folder", "")))
        if "messageCount" in entry:
            count = entry["messageCount"]
            folder += f" ({count if count is not None else 'unknown'} messages)"
        sender = source.get("sender")
        if sender:
            folder = f"{folder} · {sender}" if folder else sender
        return entry["mailbox"], folder, entry["reason"]
    return entry["mailbox"], entry["role"], entry["reason"]


def _proposalRows(plan: dict) -> list[tuple]:
    """Group identical message-level proposals into compact review rows."""
    stores = {
        archive["mailbox"]: _storeDisplay(Path(archive["root"]).name)
        for archive in plan.get("archives", [])
        if archive.get("mailbox") and archive.get("root")
    }
    grouped = {}
    for entry in plan.get("proposals", []):
        row = _proposalRow(entry, stores)
        key = row[:2] + row[3:]
        grouped[key] = grouped.get(key, 0) + 1
    return [
        (key[0], key[1], count, *key[2:])
        for key, count in sorted(grouped.items())
    ]


def _proposalRowsFiltered(plan: dict, value: str) -> list[tuple]:
    """Filter grouped Proposed Moves using a case-insensitive text match."""
    rows = _proposalRows(plan)
    terms = [term for term in value.lower().split() if term]
    if not terms:
        return rows
    return [
        row
        for row in rows
        if all(
            term in " ".join(str(cell).lower() for cell in row)
            for term in terms
        )
    ]


def _proposalRow(entry: dict, stores: dict) -> tuple:
    source, destination = entry["source"], entry["destination"]
    sender = source.get("sender", "Unknown sender")
    sourceText = f'{source["mailbox"]} IMAP/{_folderDisplay(source["folder"])}'
    destinationFolder = _folderDisplay(destination.get("folder", ""))
    if destination.get("kind") == "local":
        store = stores.get(destination.get("mailbox"), destination.get("mailbox", "Archive"))
        target = f"{store}/{destinationFolder}"
    else:
        target = f'{destination.get("mailbox", "")} IMAP/{destinationFolder}'.strip()

    classification = entry.get("classification")
    if classification:
        method = classification.get("method")
        evidence = classification.get("evidenceCount")
        reason = {
            "archiveSenderExact": "Archive history",
            "senderContainsFolderName": "Folder-name match",
            "userSenderDecision": "User decision",
        }.get(method, classification.get("reason", "Inferred"))
        if evidence and method == "archiveSenderExact":
            reason += f" ({evidence})"
    else:
        reason = (
            "Already correctly filed"
            if entry["action"] == "retain"
            else "Current folder matches archive"
        )
    if entry.get("requiresFolderCreation"):
        reason += "; create IMAP mirror"
    return (
        sourceText,
        sender,
        1,
        entry["year"],
        target,
        reason,
    )


def _folderDisplay(folder: str) -> str:
    """Render IMAP hierarchy in the user-facing slash form."""
    return folder.replace(".", "/")


## utilities


def _foldersPane(snapshot: dict) -> ComposeResult:
    """Show IMAP and configured local archive folders in one user-facing table."""
    table = DataTable(id="folders-table")
    table.add_columns("Mailbox", "Store", "Folder", "Messages", "Unseen", "Type")
    rows = 0
    for mailbox in snapshot["mailboxes"]:
        for folder in mailbox.get("folders", []):
            rows += 1
            table.add_row(
                Text(mailbox["id"]),
                Text("IMAP"),
                Text(_folderDisplay(folder["path"])),
                Text(str(folder.get("messages", ""))),
                Text(str(folder.get("unseen", ""))),
                Text(_folderKindDisplay(folder)),
            )
    for archive in snapshot.get("localArchives", []):
        if not archive.get("available"):
            rows += 1
            table.add_row(
                Text(archive["mailbox"]),
                Text(_storeDisplay(archive["name"])),
                Text("(archive unavailable)"),
                Text(""),
                Text(""),
                Text("Local archive"),
            )
            continue
        for folder in archive.get("folders", []):
            rows += 1
            table.add_row(
                Text(archive["mailbox"]),
                Text(_storeDisplay(archive["name"])),
                Text(folder["path"]),
                Text(""),
                Text(""),
                Text("Local archive"),
            )
    yield table
    if not rows:
        yield Static("No folders discovered", markup=False)


def _auditPanes(snapshot: dict) -> ComposeResult:
    """Render discovery results as user-facing tables rather than JSON."""
    with TabPane("Filters", id="filters"):
        yield from _filtersPane(snapshot)
    with TabPane("Conflicts", id="conflicts"):
        yield from _conflictsPane(snapshot)
    with TabPane("Changes", id="changes"):
        yield from _changesPane(snapshot)


def _filtersPane(snapshot: dict) -> ComposeResult:
    table = DataTable(id="filters-table")
    table.add_columns("Mailbox", "Filter", "Enabled", "Condition", "Action", "Destination")
    rows = 0
    for source in snapshot.get("sources", []):
        mailboxes = ", ".join(source.get("mailboxIds", [])) or source.get("account", "Unknown")
        for rule in source.get("filters", []):
            rows += 1
            actions = ", ".join(
                action["type"]
                + (f': {action["value"]}' if action.get("value") else "")
                for action in rule.get("actions", [])
            )
            destinations = ", ".join(
                _destinationDisplay(value) for value in rule.get("destinations", [])
            )
            table.add_row(
                Text(mailboxes),
                Text(rule.get("name", "")),
                Text(_enabledDisplay(rule.get("enabled"))),
                Text(" | ".join(rule.get("conditions", []))),
                Text(actions),
                Text(destinations),
            )
    yield table
    if not rows:
        yield Static(
            "No Thunderbird message filters discovered. "
            "Check the active Thunderbird profile if filters are expected.",
            markup=False,
        )


def _conflictsPane(snapshot: dict) -> ComposeResult:
    table = DataTable(id="conflicts-table")
    table.add_columns("Mailbox", "Filter", "Status", "Problem", "Destination")
    rows = _conflictRows(snapshot)
    for row in rows:
        table.add_row(*(Text(value) for value in row))
    yield table
    if not rows:
        yield Static("No conflicts discovered", markup=False)


def _conflictRows(snapshot: dict) -> list[tuple[str, str, str, str, str]]:
    """Return de-duplicated user-facing filter conflict rows."""
    identityMap = {}
    for source in snapshot.get("sources", []):
        for index, rule in enumerate(source.get("filters", [])):
            identity = f'{source["path"]}#{index}'
            identityMap[identity] = dict(
                filterName=rule.get("name", "Unnamed filter"),
                mailboxes=source.get("mailboxIds", []),
            )

    rows = set()
    for entry in snapshot.get("conflicts", []):
        metadata = identityMap.get(entry.get("filter", ""), {})
        name = entry.get("filterName") or metadata.get("filterName") or "Multiple filters"
        mailboxes = entry.get("mailboxes") or metadata.get("mailboxes") or []
        mailbox = ", ".join(mailboxes) if mailboxes else "Thunderbird"
        status = "Warning" if entry.get("label") == "Warning/Conflict" else entry.get("label", "")
        problem = entry.get("message", "")
        categories = entry.get("categories", [])
        if categories:
            problem += ": " + ", ".join(categories)
        rows.add(
            (
                mailbox,
                name,
                status,
                problem,
                _destinationDisplay(entry.get("target", "")),
            )
        )
    return sorted(rows, key=lambda row: (row[0], row[1], row[2], row[3], row[4]))


def _changesPane(snapshot: dict) -> ComposeResult:
    table = DataTable(id="changes-table")
    table.add_columns("Change", "Mailbox", "Item", "Before", "After")
    rows = _changeRows(snapshot)
    for row in rows:
        table.add_row(*(Text(value) for value in row))
    yield table
    if not rows:
        yield Static("No changes since the previous snapshot", markup=False)


def _changeRows(snapshot: dict) -> list[tuple[str, str, str, str, str]]:
    """Render structural changes without exposing Thunderbird storage paths."""
    sourceMap = {
        source.get("path", ""): source
        for source in snapshot.get("sources", [])
    }
    rows = []
    for entry in snapshot.get("changes", []):
        kind = entry.get("kind", "")
        identity = entry.get("identity", "")
        mailbox, item = _changeIdentityDisplay(kind, identity, sourceMap)
        rows.append(
            (
                kind,
                mailbox,
                item,
                _changeValueDisplay(entry.get("before", "")),
                _changeValueDisplay(entry.get("after", "")),
            )
        )
    return rows


def _changeIdentityDisplay(kind: str, identity, sourceMap: dict) -> tuple[str, str]:
    if kind.startswith("filter ") and isinstance(identity, (list, tuple)):
        sourcePath = str(identity[0]) if identity else ""
        filterName = str(identity[1]) if len(identity) > 1 else "Unnamed filter"
        source = sourceMap.get(sourcePath, {})
        mailboxes = source.get("mailboxIds", [])
        mailbox = ", ".join(mailboxes) or source.get("account", "Thunderbird")
        return mailbox, filterName
    return _identityDisplay(identity)


def _changeValueDisplay(value) -> str:
    if isinstance(value, list):
        return ", ".join(_destinationDisplay(str(item)) for item in value)
    return str(value)


def _storeDisplay(name: str) -> str:
    """Hide Thunderbird's .sbd storage implementation suffix."""
    return name[:-4] if name.lower().endswith(".sbd") else name


def _folderKindDisplay(folder: dict) -> str:
    attributes = [attribute.lstrip("\\") for attribute in folder.get("attributes", [])]
    if attributes:
        return ", ".join(attributes)
    return "Folder"


def _enabledDisplay(value) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Unknown"


def _destinationDisplay(value: str) -> str:
    if not value:
        return ""
    if value.startswith("imap://"):
        from urllib.parse import unquote, urlsplit

        try:
            parsed = urlsplit(value)
            return _folderDisplay(unquote(parsed.path.lstrip("/")))
        except ValueError:
            return value
    return _folderDisplay(value)


def _identityDisplay(identity) -> tuple[str, str]:
    if isinstance(identity, (list, tuple)) and len(identity) >= 2:
        return str(identity[0]), _folderDisplay(str(identity[1]))
    return "", str(identity)
