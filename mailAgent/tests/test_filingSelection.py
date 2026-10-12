"""Moving Mail multi-selection and focus navigation tests."""

import asyncio
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Input

from mailAgent.filingView import FilingEditor, FilingView


def _row(domain: str) -> dict:
    return dict(
        mailbox="andy",
        archive="myMail",
        domain=domain,
        inboxCount=1,
        parent="",
        folder="",
        canonical="",
        disposition="file",
        status="Needs choice",
        decisionSource="",
        suggestion=domain.split(".", 1)[0].title(),
        domainUncertain=False,
    )


def testSpaceSelectionAndEscapeNavigation() -> None:
    """Space toggles marks; plain clicks preserve them; Escape returns then clears."""

    class FilingApp(App):
        def compose(self) -> ComposeResult:
            snapshot = {
                "filingPlan": {
                    "rows": [_row("alpha.example"), _row("beta.example")],
                    "parents": {"andy": ["Shopping"]},
                    "proposedParents": {"andy": []},
                    "senderOverrides": [],
                }
            }
            yield FilingView(snapshot)

    async def inspect() -> None:
        app = FilingApp()
        async with app.run_test(size=(120, 30)) as pilot:
            view = app.query_one(FilingView)
            table = app.query_one("#filing-table", DataTable)
            table.focus()
            table.move_cursor(row=0)
            await pilot.press("space")
            await pilot.pause()
            assert [row["domain"] for row in view.selectedRows()] == ["alpha.example"]

            table.move_cursor(row=1)
            await pilot.pause()
            view.tableMouseUp(SimpleNamespace(button=1, ctrl=False, shift=False))
            assert [row["domain"] for row in view.selectedRows()] == ["alpha.example"]

            await pilot.press("space")
            await pilot.pause()
            assert [row["domain"] for row in view.selectedRows()] == [
                "alpha.example",
                "beta.example",
            ]
            assert len(app.query_one(FilingEditor)._rows) == 2

            app.query_one("#filing-parent", Input).focus()
            await pilot.press("escape")
            await pilot.pause()
            assert app.focused.id == "filing-table"
            assert len(view.selectedRows()) == 2

            await pilot.press("escape")
            await pilot.pause()
            assert view.selectedRows() == []

    asyncio.run(inspect())
