"""Explicit TUI for executing one reviewed live-year filing action at a time."""

import argparse
import asyncio
import imaplib
from importlib.resources import files
from pathlib import Path
import tomllib
from typing import Any

from organiseMyProjects.logUtils import setApplication
from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable, Footer, Header, Static

from mailAgent.archiveDiscovery import archiveDiscover
from mailAgent.configuration import configValidate
from mailAgent.credentials import credentialGet, credentialsLoad
from mailAgent.discovery import discoveryRun
from mailAgent.executionPlan import executionPlanPrepare
from mailAgent.executionReview import executionReviewBuild, executionReviewSelect
from mailAgent.filing import filingContextBuild, filingPlanBuild, filingRulesLoad
from mailAgent.imapExecution import imapFileExecute


def main() -> None:
    """Open the explicit execution screen; normal mailAgent remains read-only."""
    parser = parserBuild()
    args = parser.parse_args()
    setApplication("mailAgent")
    path = args.config.expanduser().absolute()
    try:
        config = configValidate(tomllib.loads(path.read_text()), path.parent)
        thunderbird = thunderbirdRoot(args.thunderbird)
        filingPlan = filingPlanFresh(config, thunderbird)
        review = executionReviewBuild(filingPlan, config)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Execution review failed: {error}\n")

    def reviewRefresh() -> dict:
        return executionReviewBuild(filingPlanFresh(config, thunderbird), config)

    def execute(actionId: str, selectedReview: dict) -> dict:
        return executionRunOne(
            actionId,
            selectedReview,
            config,
            thunderbird,
            clientFactory=imaplib.IMAP4_SSL,
        )

    ExecutionApp(review, reviewRefresh, execute).run()


def parserBuild() -> argparse.ArgumentParser:
    """Define the separate mutation-capable TUI arguments."""
    parser = argparse.ArgumentParser(
        description="Review and explicitly execute one safe mail filing action"
    )
    parser.add_argument(
        "--config", type=Path, default=Path.home() / ".config/mailAgent/config.toml"
    )
    parser.add_argument(
        "--thunderbird", type=Path, default=Path.home() / ".thunderbird"
    )
    return parser


class ExecutionApp(App):
    """Review one live-year filing action and execute only the selected row."""

    TITLE = "mailAgent Execute"
    BINDINGS = [("q", "quit", "Quit")]
    CSS_PATH = files("organiseMyProjects").joinpath("myStyles.css")

    def __init__(self, review: dict, reviewRefresh, execute) -> None:
        super().__init__()
        self.review = review
        self.reviewRefresh = reviewRefresh
        self.execute = execute

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "EXECUTION MODE · selected mail can be moved. Only one reviewed live-year "
            "File action is executed at a time.",
            id="execution-safety",
            markup=False,
        )
        yield Static(self.summaryText(), id="execution-summary", markup=False)
        table = DataTable(id="execution-table", cursor_type="row")
        table.styles.height = "1fr"
        table.add_columns("Mailbox", "Sender", "Year", "Destination", "Create", "Action")
        for row in self.tableRows():
            table.add_row(*(Text(value) for value in row))
        yield table
        yield Button("Refresh review", id="execution-refresh")
        yield Button(
            "Execute selected mail change",
            id="execution-run",
            variant="error",
            disabled=not bool(self.review.get("candidates")),
        )
        yield Static("", id="execution-status", markup=False)
        yield Footer()

    def summaryText(self) -> str:
        """Explain exactly what this first execution increment can change."""
        count = len(self.review.get("candidates", []))
        blocked = len(self.review.get("blocked", []))
        return (
            f"{count} executable live-year File actions · {blocked} blocked. "
            "Older/local archive filing, Ignore and Junk execution are not enabled here."
        )

    def tableRows(self) -> list[tuple[str, ...]]:
        """Return concise user-readable reviewed actions."""
        return [
            (
                str(candidate["mailbox"]),
                str(candidate.get("sender") or candidate.get("domain") or "unknown"),
                str(candidate["year"]),
                str(candidate["canonical"]),
                "Yes" if candidate["createFolder"] else "No",
                candidate["actionId"][:12],
            )
            for candidate in self.review.get("candidates", [])
        ]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Refresh safely or explicitly execute the currently selected action."""
        if event.button.id == "execution-refresh":
            self.workerStart("Refreshing execution review…", self.reviewRefresh, False)
            return
        if event.button.id != "execution-run":
            return
        table = self.query_one("#execution-table", DataTable)
        row = table.cursor_row
        candidates = self.review.get("candidates", [])
        if row < 0 or row >= len(candidates):
            self.query_one("#execution-status", Static).update(
                "Select an execution row first."
            )
            return
        actionId = candidates[row]["actionId"]
        selectedReview = self.review
        self.workerStart(
            "Executing selected mail change…",
            lambda: self.execute(actionId, selectedReview),
            True,
        )

    def workerStart(self, message: str, operation, executed: bool) -> None:
        """Run blocking IMAP work away from the Textual event loop."""
        self.query_one("#execution-run", Button).disabled = True
        self.query_one("#execution-refresh", Button).disabled = True
        self.query_one("#execution-status", Static).update(message)
        self.run_worker(
            self.workerRun(operation, executed),
            group="mail-execution",
            exclusive=True,
        )

    async def workerRun(self, operation, executed: bool) -> None:
        """Finish one operation, then rebuild the review from fresh discovery."""
        status = self.query_one("#execution-status", Static)
        try:
            result = await asyncio.to_thread(operation)
            refreshed = await asyncio.to_thread(self.reviewRefresh)
            self.review = refreshed
            self.reviewShow()
            if executed:
                state = result.get("state", "unknown") if isinstance(result, dict) else "unknown"
                status.update(f"Execution finished: {state}. Review refreshed.")
            else:
                status.update("Execution review refreshed.")
        except Exception as error:
            status.update(f"Execution blocked or failed: {error}")
        finally:
            self.query_one("#execution-refresh", Button).disabled = False
            self.query_one("#execution-run", Button).disabled = not bool(
                self.review.get("candidates")
            )

    def reviewShow(self) -> None:
        """Replace the review rows without leaving execution mode."""
        table = self.query_one("#execution-table", DataTable)
        table.clear(columns=False)
        for row in self.tableRows():
            table.add_row(*(Text(value) for value in row))
        self.query_one("#execution-summary", Static).update(self.summaryText())


def executionRunOne(
    actionId: str,
    review: dict,
    config: dict,
    thunderbird: Path,
    *,
    clientFactory=imaplib.IMAP4_SSL,
) -> dict:
    """Execute one reviewed action after fresh revalidation on an owned connection."""
    fullId, approved = executionReviewSelect(review, actionId)
    candidate = next(
        candidate for candidate in review["candidates"] if candidate["actionId"] == fullId
    )
    account = next(
        account for account in config["mailboxes"] if account["id"] == candidate["mailbox"]
    )
    credentials = credentialsLoad(
        Path(config["general"]["credentialsFile"])
        if config["general"].get("credentialsFile")
        else None,
        sessionCache=bool(config["general"].get("credentialsSessionCache")),
    )
    client = None
    try:
        password = credentialGet(account, credentials=credentials)
        try:
            client = clientFactory(
                account["host"], account.get("port", 993), timeout=30
            )
            client.login(account["username"], password)
        finally:
            del password

        def observe() -> dict:
            filingPlan = filingPlanFresh(config, thunderbird)
            return executionPlanPrepare(filingPlan, config)

        return imapFileExecute(
            client,
            approved,
            config,
            observe,
            fullId,
            confirm=True,
        )
    finally:
        credentials.clear()
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass


def filingPlanFresh(config: dict, thunderbird: Path) -> dict:
    """Rebuild filing eligibility entirely from current read-only observations."""
    options: dict[str, Any] = dict(includeMessages=True, includeInbox=True)
    if config["general"].get("credentialsFile"):
        options["credentialsFile"] = Path(config["general"]["credentialsFile"])
    if config["general"].get("credentialsSessionCache"):
        options["credentialsSessionCache"] = True
    snapshot = discoveryRun(config["mailboxes"], thunderbird, **options)
    if any(mailbox.get("failed") for mailbox in snapshot["mailboxes"]):
        raise ValueError("Mailbox discovery is incomplete; execution is blocked")
    snapshot["localArchives"] = localArchivesDiscover(config)
    context = filingContextBuild(config)
    return filingPlanBuild(context, snapshot, filingRulesLoad())


def localArchivesDiscover(config: dict) -> list[dict]:
    """Discover authoritative personal archives without changing them."""
    archives = []
    for account in config["mailboxes"]:
        if account.get("role") != "personal" or not account.get("localArchive"):
            continue
        root = Path(account["localArchive"])
        archive = archiveDiscover(root)
        archives.append(
            dict(
                mailbox=account["id"],
                name=root.name,
                root=str(root),
                format=archive["format"],
                available=archive["available"],
                complete=archive.get("complete", True),
                folders=archive.get("folders", []),
                issues=archive.get("issues", []),
            )
        )
    return archives


def thunderbirdRoot(configured: Path) -> Path:
    """Resolve native or Flatpak Thunderbird metadata root."""
    configured = configured.expanduser()
    if (configured / "profiles.ini").is_file():
        return configured
    if configured == Path.home() / ".thunderbird":
        for candidate in (
            Path.home() / ".var/app/org.mozilla.thunderbird_esr/.thunderbird",
            Path.home() / ".var/app/org.mozilla.Thunderbird/.thunderbird",
        ):
            if (candidate / "profiles.ini").is_file():
                return candidate
    return configured
