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
                if "migrationPlan" in snapshot:
                    yield from _planningPanes(snapshot["migrationPlan"])
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
    """Always show planning controls and the latest readable plan summary."""
    with TabPane("Plan", id="plan"):
        with VerticalScroll():
            yield Button(
                "Run planning session",
                id="run-planning",
                variant="primary",
            )
            if plan is None:
                yield Static(
                    "No planning session has been run in this view.",
                    id="plan-summary",
                    markup=False,
                )
            else:
                yield Static(
                    "\n".join(planSummaryLines(plan)),
                    id="plan-summary",
                    markup=False,
                )


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


def _planningPanes(plan: dict) -> ComposeResult:
    specifications = (
        (
            "Mapping",
            "mappings",
            "Inferred · Canonical archive taxonomy",
            ("Mailbox", "Canonical folder", "Local store", "IMAP folder", "Status"),
        ),
        (
            "Proposed Moves",
            "proposals",
            "Inferred · Review proposals; execution disabled",
            ("Source", "Year", "Action", "Destination", "Review"),
        ),
        (
            "Review Queue",
            "reviewQueue",
            "Warning/Conflict · Resolve before migration",
            ("Mailbox", "Folder / message", "Reason"),
        ),
        (
            "Role Boundaries",
            "excluded",
            "Observed configuration · Available in Mailbox Audit",
            ("Mailbox", "Role", "Policy"),
        ),
    )
    for title, key, label, columns in specifications:
        with TabPane(title, id=key):
            yield Static(label, markup=False)
            if key == "proposals" and "summary" in plan:
                yield Static(json.dumps(plan["summary"], indent=2), markup=False)
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
            "issue", "Existing mirror" if entry["imapExists"] else "Mirror proposed"
        )
        return (
            entry["mailbox"],
            entry["canonical"],
            entry["local"],
            entry["imap"] or "Unavailable",
            status,
        )
    if key == "proposals":
        source, destination = entry["source"], entry["destination"]
        origin = f'{source["mailbox"]}: {source["folder"]} (UID {source["uid"]})'
        target = destination.get(
            "path", f'{destination["mailbox"]}: {destination["folder"]}'
        )
        review = (
            "Folder creation required"
            if entry["requiresFolderCreation"]
            else (
                "Confirmation and verification required"
                if entry["requiresConfirmation"]
                else "Keep on server"
            )
        )
        return origin, entry["year"], entry["action"], target, review
    if key == "reviewQueue":
        source = entry.get("source", {})
        folder = source.get("folder", entry.get("folder", ""))
        if "messageCount" in entry:
            count = entry["messageCount"]
            folder += f" ({count if count is not None else 'unknown'} messages)"
        if source.get("uid"):
            folder += " (UID " + source["uid"] + ")"
        return entry["mailbox"], folder, entry["reason"]
    return entry["mailbox"], entry["role"], entry["reason"]
