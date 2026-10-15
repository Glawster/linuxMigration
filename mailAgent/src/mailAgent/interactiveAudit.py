"""Interactive audit wrapper that refreshes plans and executes reviewed filing."""

import asyncio
from typing import Callable

from rich.text import Text
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Input, ProgressBar, Select, Static

import mailAgent.auditUi as auditUi
from mailAgent.auditUi import (
    _planActionText,
    _planningEntries,
    _planningRow,
    _proposalRows,
    _proposalRowsFiltered,
    auditAppBuild as _auditAppBuild,
)
from mailAgent.digestInteraction import DigestPolicyTable
from mailAgent.executionBatch import executionBatchRun
from mailAgent.filingView import FilingView
from mailAgent.planSummary import planSummaryLines
from mailAgent.version import applicationVersion


def auditAppBuild(
    snapshot: dict,
    planRefresh: Callable[[], dict] | None = None,
    filingExecution: dict | None = None,
):
    """Build the audit app with optional plan refresh and Moving Mail execution."""
    # Keep the presentation module UI-independent from this richer keyboard layer.
    # _interestPane resolves this class at composition time, so the interactive CLI
    # consistently gets the standardized digest controls whether or not a plan exists.
    auditUi._DigestPolicyTable = DigestPolicyTable
    baseApp = _auditAppBuild(snapshot)
    baseApp.TITLE = f"Mailbox Audit · mailAgent {applicationVersion()}"
    if planRefresh is None and filingExecution is None:
        return baseApp

    baseClass = type(baseApp)

    class InteractiveMailboxAudit(baseClass):
        """Mailbox audit with refresh and explicitly invoked filing execution."""

        TITLE = f"Mailbox Audit · mailAgent {applicationVersion()}"

        async def on_mount(self) -> None:
            if filingExecution is None:
                return
            pane = self.query_one("#inboxFiling")
            refresh = Button("Refresh review", id="filing-execution-refresh")
            selected = Button("Execute Selected", id="filing-execution-selected")
            runAll = Button("Execute All", id="filing-execution-all")
            for button in (refresh, selected, runAll):
                button.styles.width = "1fr"
            actions = Horizontal(
                refresh,
                selected,
                runAll,
                id="filing-execution-actions",
            )
            actions.styles.height = 3
            actions.styles.padding = (1, 1)
            progress = ProgressBar(
                total=1,
                show_eta=False,
                id="filing-execution-progress",
            )
            progress.styles.height = 1
            progress.styles.display = "none"
            await pane.mount(actions)
            await pane.mount(progress)
            await pane.mount(Static("", id="filing-execution-status", markup=False))
            self.query_one("#safety", Static).update(
                "Audit views are read-only · Moving Mail can execute explicitly reviewed moves"
            )

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "refresh-planning" and planRefresh is not None:
                # Textual dispatches to base-class handlers unless prevented.
                event.prevent_default()
                _planRefreshStart(self, snapshot, planRefresh)
                return
            if filingExecution is None:
                return
            if event.button.id == "filing-execution-refresh":
                event.prevent_default()
                self._filingExecutionStart("refresh")
                return
            if event.button.id == "filing-execution-selected":
                event.prevent_default()
                self._filingExecutionStart("selected")
                return
            if event.button.id == "filing-execution-all":
                event.prevent_default()
                self._filingExecutionStart("all")
                return

        def _filingExecutionStart(self, mode: str) -> None:
            for identity in (
                "#filing-execution-refresh",
                "#filing-execution-selected",
                "#filing-execution-all",
            ):
                self.query_one(identity, Button).disabled = True
            status = self.query_one("#filing-execution-status", Static)
            message = {
                "refresh": "Refreshing Moving Mail…",
                "selected": "Preparing selected Moving Mail row(s)…",
                "all": "Preparing all reviewed Moving Mail…",
            }[mode]
            status.update(message)
            self.run_worker(
                self._filingExecutionRun(mode),
                group="moving-mail-execution",
                exclusive=True,
            )

        async def _filingExecutionRun(self, mode: str) -> None:
            status = self.query_one("#filing-execution-status", Static)
            progress = self.query_one("#filing-execution-progress", ProgressBar)
            logger = filingExecution.get("logger") if filingExecution else None
            try:
                if mode == "refresh":
                    refreshedSnapshot = await asyncio.to_thread(
                        filingExecution["snapshotRefresh"]
                    )
                    snapshot.clear()
                    snapshot.update(refreshedSnapshot)
                    self.query_one(FilingView).planShow()
                    progress.styles.display = "none"
                    status.update("Moving Mail refreshed.")
                    if logger is not None:
                        logger.info("Moving Mail review refreshed")
                    return

                review = await asyncio.to_thread(filingExecution["reviewRefresh"])
                if mode == "selected":
                    review = self._filingSelectedReview(review)
                requested = len(review.get("candidates", []))
                domains = {
                    (
                        str(candidate.get("mailbox") or ""),
                        str(candidate.get("domain") or ""),
                    )
                    for candidate in review.get("candidates", [])
                }
                if requested == 0:
                    progress.styles.display = "none"
                    status.update("No executable reviewed mail matches this selection.")
                    if logger is not None:
                        logger.info("Moving Mail Execute Selected: no executable messages matched")
                    return

                label = "Selected" if mode == "selected" else "All"
                domainText = "domain" if len(domains) == 1 else "domains"
                status.update(
                    f"Execute {label}: {requested} messages across "
                    f"{len(domains)} {domainText}."
                )
                if logger is not None:
                    logger.info(
                        f"Moving Mail Execute {label}: {requested} messages across "
                        f"{len(domains)} {domainText}"
                    )
                progress.styles.display = "block"
                progress.update(total=requested, progress=0)

                result = await asyncio.to_thread(
                    executionBatchRun,
                    review,
                    filingExecution["reviewRefresh"],
                    filingExecution["execute"],
                    lambda completed, total: self.call_from_thread(
                        self._filingProgressUpdate, completed, total
                    ),
                    logger,
                )
                refreshedSnapshot = await asyncio.to_thread(
                    filingExecution["snapshotRefresh"]
                )
                snapshot.clear()
                snapshot.update(refreshedSnapshot)
                self.query_one(FilingView).planShow()
                message = (
                    f'Execute {label} finished: {result.get("completed", 0)}/'
                    f'{result.get("requested", 0)} completed.'
                )
                status.update(message)
                if logger is not None:
                    logger.info("Moving Mail " + message)
            except Exception as error:
                message = "Moving Mail execution blocked or failed: " + str(error)
                status.update(message)
                if logger is not None:
                    logger.error(message)
            finally:
                for identity in (
                    "#filing-execution-refresh",
                    "#filing-execution-selected",
                    "#filing-execution-all",
                ):
                    self.query_one(identity, Button).disabled = False

        def _filingSelectedReview(self, review: dict) -> dict:
            """Restrict execution to messages represented by selected domain row(s)."""
            view = self.query_one(FilingView)
            rows = view.selectedRows()
            if not rows:
                selected = view._selectedRow()
                rows = [selected] if selected else []
            identities = {
                (str(row.get("mailbox") or ""), str(row.get("domain") or ""))
                for row in rows
                if row
            }
            selectedReview = dict(review)
            selectedReview["candidates"] = [
                candidate
                for candidate in review.get("candidates", [])
                if (
                    str(candidate.get("mailbox") or ""),
                    str(candidate.get("domain") or ""),
                )
                in identities
            ]
            return selectedReview

        def _filingProgressUpdate(self, completed: int, requested: int) -> None:
            progress = self.query_one("#filing-execution-progress", ProgressBar)
            progress.styles.display = "block"
            progress.update(total=max(requested, 1), progress=completed)

    return InteractiveMailboxAudit()


def auditShow(
    snapshot: dict,
    planRefresh: Callable[[], dict] | None = None,
    filingExecution: dict | None = None,
) -> str | None:
    """Display audit TUI with optional refresh and reviewed filing execution."""
    return auditAppBuild(snapshot, planRefresh, filingExecution).run()


def _planRefreshStart(
    app,
    snapshot: dict,
    planRefresh: Callable[[], dict],
) -> None:
    """Start one background plan refresh while leaving the current TUI mounted."""
    button = app.query_one("#refresh-planning", Button)
    button.disabled = True
    app.query_one("#plan-generated", Static).update("Refreshing plan…")
    app.run_worker(
        _planRefresh(app, snapshot, planRefresh),
        group="plan-refresh",
        exclusive=True,
    )


async def _planRefresh(
    app,
    snapshot: dict,
    planRefresh: Callable[[], dict],
) -> None:
    """Run synchronous discovery off the UI loop and replace plan widgets in place."""
    button = app.query_one("#refresh-planning", Button)
    status = app.query_one("#plan-generated", Static)
    try:
        refreshed = await asyncio.to_thread(planRefresh)
        plan = refreshed["migrationPlan"]
        _planWidgetsUpdate(app, plan)
        snapshot.clear()
        snapshot.update(refreshed)
        refresher = getattr(app, "_filingRefresh", None)
        if refresher:
            refresher()
        status.update("Plan refreshed · " + plan.get("generatedAt", "time unavailable"))
    except Exception as error:
        # UI boundary: preserve the existing plan on any refresh failure.
        status.update("Plan refresh failed · " + str(error))
    finally:
        button.disabled = False


def _planWidgetsUpdate(app, plan: dict) -> None:
    """Refresh existing Plan widgets without replacing tabs or filter controls."""
    guidance = app.query_one("#plan-action", Static)
    text = _planActionText(plan)
    guidance.update(text)
    needed = text.startswith("⚠")
    guidance.set_class(needed, "warning")
    guidance.set_class(needed, "action-needed")
    app.query_one("#plan-summary", Static).update("\n".join(planSummaryLines(plan)))

    proposalFilter = app.query_one("#proposal-filter", Input).value
    proposalRows = _proposalRowsFiltered(plan, proposalFilter)
    _tableReplace(app.query_one("#proposal-table", DataTable), proposalRows)
    app.query_one("#proposal-filter-status", Static).update(
        f"Showing {len(proposalRows)} of {len(_proposalRows(plan))} grouped moves"
    )

    _paneTableReplace(app, "mappings", plan, "mappings")
    _paneTableReplace(app, "reviewQueue", plan, "reviewQueue")
    _paneTableReplace(app, "roleBoundaries", plan, "roleBoundaries")

    chooser = app.query_one("#review-folder", Select)
    if hasattr(chooser, "set_options"):
        chooser.set_options(
            [
                (
                    f'{mapping["mailbox"]} — {mapping["canonical"]}',
                    (mapping["mailbox"], mapping["canonical"]),
                )
                for mapping in plan["mappings"]
                if mapping.get("localSelectable")
            ]
        )


def _paneTableReplace(app, paneId: str, plan: dict, key: str) -> None:
    pane = app.query_one("#" + paneId)
    table = pane.query_one(DataTable)
    rows = [_planningRow(key, entry) for entry in _planningEntries(plan, key)]
    _tableReplace(table, rows)


def _tableReplace(table: DataTable, rows: list[tuple]) -> None:
    table.clear(columns=False)
    for row in rows:
        table.add_row(*(Text(str(cell)) for cell in row))
