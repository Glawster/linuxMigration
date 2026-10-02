"""Presentation only for the core audit and planning models."""

import json

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane

## presentation


def auditAppBuild(snapshot: dict) -> App:
    """Construct the audit app for interactive use or headless validation."""

    class MailboxAudit(App):
        TITLE = "Mailbox Audit"
        BINDINGS = [("q", "quit", "Quit")]

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
                yield from _auditPanes(snapshot)
                if "migrationPlan" in snapshot:
                    yield from _planningPanes(snapshot["migrationPlan"])
            yield Footer()

    return MailboxAudit()


def auditShow(snapshot: dict) -> None:
    """Display audit facts, canonical mappings, proposals and review issues."""
    auditAppBuild(snapshot).run()


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
        if source.get("uid"):
            folder += " (UID " + source["uid"] + ")"
        return entry["mailbox"], folder, entry["reason"]
    return entry["mailbox"], entry["role"], entry["reason"]
