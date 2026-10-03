"""Presentation only for the core audit and planning models."""

from rich.text import Text
from textual.binding import Binding
from textual.app import App, ComposeResult
from textual.coordinate import Coordinate
from textual.containers import VerticalScroll
from textual.widgets import Button, DataTable, Footer, Header, Static, TabbedContent, TabPane

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

        def on_button_pressed(self, event: Button.Pressed) -> None:
            """Return a planning request to the CLI when the Plan button is used."""
            if event.button.id in ("run-planning", "refresh-planning"):
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
            "Review what mailAgent proposes; execution is disabled",
            ("Mailbox", "Sender", "Year", "Action", "Destination", "Reason"),
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
            table = DataTable()
            table.add_columns(*columns)
            for entry in plan[key]:
                table.add_row(*(Text(str(cell)) for cell in _planningRow(key, entry)))
            yield table
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
        source, destination = entry["source"], entry["destination"]
        sender = source.get("sender", "Unknown sender")
        destinationFolder = _folderDisplay(destination.get("folder", ""))
        target = (
            f'{destination["mailbox"]}: {destinationFolder}'
            if destination.get("mailbox")
            else destinationFolder
        )
        action = {
            "migrate": "Move",
            "archive": "Archive",
            "retain": "Keep",
        }.get(entry["action"], entry["action"].title())
        classification = entry.get("classification")
        reason = (
            classification.get("reason", "")
            if classification
            else (
                "Already in the correct folder"
                if entry["action"] == "retain"
                else "Current folder matches archive taxonomy"
            )
        )
        if entry["requiresFolderCreation"]:
            reason = (reason + "; create destination folder").strip("; ")
        return (
            source["mailbox"],
            sender,
            entry["year"],
            action,
            target,
            reason,
        )
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
