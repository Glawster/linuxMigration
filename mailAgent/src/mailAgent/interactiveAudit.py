"""Interactive audit wrapper that refreshes plans without dropping the TUI."""

import asyncio
from typing import Callable

from rich.text import Text
from textual.widgets import Button, DataTable, Input, Select, Static

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
from mailAgent.planSummary import planSummaryLines


def auditAppBuild(
    snapshot: dict,
    planRefresh: Callable[[], dict] | None = None,
):
    """Build the audit app and optionally add in-place plan refresh support."""
    # Keep the presentation module UI-independent from this richer keyboard layer.
    # _interestPane resolves this class at composition time, so the interactive CLI
    # consistently gets the standardized digest controls whether or not a plan exists.
    auditUi._DigestPolicyTable = DigestPolicyTable
    baseApp = _auditAppBuild(snapshot)
    if planRefresh is None:
        return baseApp

    baseClass = type(baseApp)

    class InteractiveMailboxAudit(baseClass):
        """Mailbox audit with an in-place refresh handler registered on the class."""

        def on_button_pressed(self, event: Button.Pressed) -> None:
            if event.button.id == "refresh-planning":
                # Textual dispatches to base-class handlers unless prevented.
                event.prevent_default()
                _planRefreshStart(self, snapshot, planRefresh)
                return

    return InteractiveMailboxAudit()


def auditShow(
    snapshot: dict,
    planRefresh: Callable[[], dict] | None = None,
) -> str | None:
    """Display the audit TUI and keep it active while refreshing a stored plan."""
    return auditAppBuild(snapshot, planRefresh).run()


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
    app.query_one("#plan-action", Static).update(_planActionText(plan))
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
