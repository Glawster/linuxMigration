"""Moving Mail multi-selection, default Parent and focus navigation tests."""

import asyncio
from types import SimpleNamespace

from textual.app import App, ComposeResult
from textual.widgets import DataTable, Input

from mailAgent.filingView import FilingEditor, FilingView


def _row(domain: str, parent: str = "", folder: str = "") -> dict:
    canonical = f"{parent}/{folder}" if parent and folder else ""
    return dict(
        mailbox="andy",
        archive="myMail",
        domain=domain,
        inboxCount=1,
        parent=parent,
        folder=folder,
        canonical=canonical,
        disposition="file",
        status="Existing" if canonical else "Needs choice",
        decisionSource="domain" if canonical else "",
        suggestion=domain.split(".", 1)[0].title(),
        domainUncertain=False,
    )


def _snapshot(rows: list[dict]) -> dict:
    return {
        "filingPlan": {
            "rows": rows,
            "parents": {"andy": ["Shopping"]},
            "proposedParents": {"andy": []},
            "senderOverrides": [],
        }
    }


def testSpaceSelectionAndEscapeNavigation() -> None:
    """Space toggles marks; plain clicks preserve them; Escape returns then clears."""

    class FilingApp(App):
        def compose(self) -> ComposeResult:
            yield FilingView(_snapshot([_row("alpha.example"), _row("beta.example")]))

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


def testDefaultParentCanBeSetAndAppliedWithZ() -> None:
    """Shift+Z learns a Parent from the row; z prefills it on another row."""

    class FilingApp(App):
        def compose(self) -> ComposeResult:
            yield FilingView(
                _snapshot(
                    [
                        _row("shop.example", "Shopping", "Shop"),
                        _row("beta.example"),
                    ]
                )
            )

    async def inspect() -> None:
        app = FilingApp()
        async with app.run_test(size=(120, 30)) as pilot:
            view = app.query_one(FilingView)
            table = app.query_one("#filing-table", DataTable)
            editor = app.query_one(FilingEditor)
            table.focus()
            table.move_cursor(row=0)
            await pilot.press("shift+z")
            await pilot.pause()
            assert view._defaultParent == "Shopping"

            table.move_cursor(row=1)
            await pilot.pause()
            await pilot.press("z")
            await pilot.pause()
            assert app.query_one("#filing-parent", Input).value == "Shopping"
            assert app.query_one("#filing-child", Input).value == "Beta"
            assert editor._disposition == "file"
            assert app.focused.id == "filing-child"

    asyncio.run(inspect())


def testDefaultParentReportsMissingSourceParent() -> None:
    """Shift+Z refuses to create a default from an unresolved row."""

    class FilingApp(App):
        def compose(self) -> ComposeResult:
            yield FilingView(_snapshot([_row("alpha.example")]))

    async def inspect() -> None:
        app = FilingApp()
        async with app.run_test(size=(120, 30)) as pilot:
            view = app.query_one(FilingView)
            table = app.query_one("#filing-table", DataTable)
            table.focus()
            await pilot.press("shift+z")
            await pilot.pause()
            assert view._defaultParent is None
            assert "no Parent" in str(app.query_one("#filing-status").render())

    asyncio.run(inspect())
