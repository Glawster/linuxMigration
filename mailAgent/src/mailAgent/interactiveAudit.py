"""Interactive audit wrapper that refreshes plans without dropping the TUI."""

import asyncio
from types import MethodType
from typing import Callable

from rich.text import Text
from textual.widgets import Button, DataTable, Input, Select, Static

from mailAgent.auditUi import (
    _planningRow,
    _proposalRows,
    _proposalRowsFiltered,
    auditAppBuild as _auditAppBuild,
)
from mailAgent.planSummary import planSummaryLines


PlanRefresh = Callable[[], dict]


def auditAppBuild(snapshot: dict, planRefresh: PlanRefresh | None = None):
    """Build the audit app and optionally add in-place plan refresh support."""
    app = _auditAppBuild(snapshot)
    if planRefresh is None:
        return app

    originalButtonHandler = app.on_button_pressed

    def onButtonPressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh-planning":
            _planRefreshStart(self, snapshot, planRefresh)
            return
        originalButtonHandler(event)

    app.on_button_pressed = MethodType(onButtonPressed, app)
    return app


def auditShow(snapshot: dict, planRefresh: PlanRefresh | None = None) -> str | None:
    """Display the audit TUI and keep it active while refreshing a stored plan."""
    return auditAppBuild(snapshot, planRefresh).run()


def _planRefreshStart(app, snapshot: dict, planRefresh: PlanRefresh) -> None:
    """Start one background plan refresh while leaving the current TUI mounted."""
    button = app.query_one("#refresh-planning", Button)
    button.disabled = True
    generated = app.query_one("#plan-generated", Static)
    generated.update("Refreshing plan…")
    app.run_worker(
        _planRefresh(app, snapshot, planRefresh),
        group="plan-refresh",
        exclusive=True,
    )


async def _planRefresh(app, snapshot: dict, planRefresh: PlanRefresh) -> None:
    """Run synchronous discovery off the UI loop and replace plan widgets in place."""
    button = app.query_one("#refresh-planning", Button)
    generated = app.query_one("#plan-generated", Static)
    try:
        refreshed = await asyncio.to_thread(planRefresh)
        plan = refreshed["migrationPlan"]
        snapshot.clear()
        snapshot.update(refreshed)
        _planWidgetsUpdate(app, plan)
        generated.update("Plan refreshed · " + plan.get("generatedAt", "time unavailable"))
    except (OSError, ValueError, KeyError) as error:
        generated.update("Plan refresh failed · " + str(error))
    finally:
        button.disabled = False


def _planWidgetsUpdate(app, plan: dict) -> None:
    """Refresh existing Plan widgets without replacing tabs or filter controls."""
    app.query_one("#plan-summary", Static).update("\n".join(planSummaryLines(plan)))

    proposalFilter = app.query_one("#proposal-filter", Input).value
    proposalRows = _proposalRowsFiltered(plan, proposalFilter)
    _tableReplace(app.query_one("#proposal-table", DataTable), proposalRows)
    app.query_one("#proposal-filter-status", Static).update(
        f"Showing {len(proposalRows)} of {len(_proposalRows(plan))} grouped moves"
    )

    _paneTableReplace(app, "mappings", plan, "mappings")
    _paneTableReplace(app, "reviewQueue", plan, "reviewQueue")
    _paneTableReplace(app, "excluded", plan, "excluded")

    chooser = app.query_one("#review-folder", Select)
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
    rows = [_planningRow(key, entry) for entry in plan[key]]
    _tableReplace(table, rows)


def _tableReplace(table: DataTable, rows: list[tuple]) -> None:
    table.clear(columns=False)
    for row in rows:
        table.add_row(*(Text(str(cell)) for cell in row))
