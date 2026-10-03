"""Presentation only for the core audit and planning models."""

import json

from rich.text import Text
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
            ("space", "toggle_interest", "Toggle interesting sender"),
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
                    with TabbedContent():
                        for index, mailbox in enumerate(snapshot["mailboxes"]):
                            with TabPane(mailbox["name"], id=f"mailbox-{index}"):
                                with VerticalScroll():
                                    yield Static(
                                        "Observed\n" + json.dumps(mailbox, indent=2),
                                        markup=False,
                                    )
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
            if event.button.id == "run-planning":
                self.exit("runPlanning")

    return MailboxAudit()


def auditShow(snapshot: dict) -> str | None:
    """Display audit facts and return any requested follow-up workflow."""
    return auditAppBuild(snapshot).run()


def _interestPane(senderRows: list[dict], issue: str | None) -> ComposeResult:
    with TabPane("Inbox Interest", id="inboxInterest"):
        yield Static(
            "Select a sender row and press Space to toggle ✓ Interesting. "
            "Interesting senders are candidates for the daily digest.",
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
                    "Run planning session",
                    id="run-planning",
                    variant="primary",
                )
            return

        with TabbedContent(id="plan-menu"):
            with TabPane("Summary", id="planSummary"):
                with VerticalScroll():
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


def _auditPanes(snapshot: dict) -> ComposeResult:
    for title, key in (
        ("Filters", "sources"),
        ("Conflicts", "conflicts"),
        ("Quota", "mailboxes"),
        ("Changes", "changes"),
    ):
        with TabPane(title, id=title.lower()):
            value = snapshot[key]
            if title == "Quota":
                value = [
                    {"mailbox": m["name"], "quota": m["quota"], "issues": m["issues"]}
                    for m in value
                ]
            with VerticalScroll():
                yield Static(
                    (
                        "Warning/Conflict and Inferred"
                        if title == "Conflicts"
                        else "Observed"
                    )
                    + "\n"
                    + json.dumps(value, indent=2),
                    markup=False,
                )

