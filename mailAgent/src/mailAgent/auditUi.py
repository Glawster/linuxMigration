"""Presentation only for the core audit model."""

import json

from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Static, TabbedContent, TabPane

## presentation


def auditShow(snapshot: dict) -> None:
    """Display independently navigable mailbox folders and audit results."""

    class MailboxAudit(App):
        TITLE = "Mailbox Audit"
        BINDINGS = [("q", "quit", "Quit")]

        def compose(self) -> ComposeResult:
            yield Header()
            with TabbedContent():
                with TabPane("Folders"):
                    with TabbedContent():
                        for index, mailbox in enumerate(snapshot["mailboxes"]):
                            with TabPane(mailbox["name"], id=f"mailbox-{index}"):
                                with VerticalScroll():
                                    yield Static(
                                        "Observed\n" + json.dumps(mailbox, indent=2)
                                    )
                for title, key in (
                    ("Filters", "sources"),
                    ("Conflicts", "conflicts"),
                    ("Quota", "mailboxes"),
                    ("Changes", "changes"),
                ):
                    with TabPane(title):
                        value = snapshot[key]
                        if title == "Quota":
                            value = [
                                {
                                    "mailbox": m["name"],
                                    "quota": m["quota"],
                                    "issues": m["issues"],
                                }
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
                                + json.dumps(value, indent=2)
                            )
            yield Footer()

    MailboxAudit().run()
