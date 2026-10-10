"""Presentation-model checks for the Moving Mail table and editor text."""

from mailAgent.filingView import (
    _actionText,
    _columnSpecs,
    _headingText,
    _rowAction,
    _rowStatus,
    _tableCells,
)


def testUnresolvedRowUsesChooseAction() -> None:
    row = {
        "domain": "example.com",
        "archive": "kathyMail",
        "inboxCount": 2,
        "status": "Needs choice",
        "disposition": "file",
    }

    assert _rowAction(row) == "Choose"
    assert _rowStatus(row) == ""
    cells = _tableCells(row, 12)
    assert str(cells[6]) == "Choose"
    assert str(cells[7]) == ""


def testFileRowSeparatesActionFromStatus() -> None:
    row = {
        "domain": "hsnci.net",
        "archive": "kathyMail",
        "inboxCount": 5,
        "parent": "Health",
        "folder": "Southern Trust",
        "canonical": "Health/Southern Trust",
        "status": "Proposed child",
        "disposition": "file",
    }

    assert _rowAction(row) == "File"
    assert _rowStatus(row) == "Proposed child"


def testIgnoreAndJunkAreActionsNotStatuses() -> None:
    ignored = {"disposition": "ignore", "status": "Ignore"}
    junk = {"disposition": "junk", "status": "Junk"}

    assert _rowAction(ignored) == "Ignore"
    assert _rowStatus(ignored) == ""
    assert _rowAction(junk) == "Junk"
    assert _rowStatus(junk) == ""


def testActionColumnIsBeforeStatus() -> None:
    columns = [name for name, _label, _width in _columnSpecs()]

    assert columns[-2:] == ["action", "status"]


def testActionBannerExplainsKeyboardChoices() -> None:
    text = _actionText([{"status": "Needs choice", "disposition": "file"}])

    assert "1 domains need an action" in text
    assert "i Ignore" in text
    assert "j Junk" in text


def testSelectedHeadingUsesSelectedLabel() -> None:
    text = _headingText(
        {"domain": "hsnci.net", "archive": "kathyMail", "inboxCount": 5}
    )

    assert text == "Selected: hsnci.net · kathyMail · 5 messages"


def testEditorMountAndActionTransitionsKeepFieldsConsistent(monkeypatch) -> None:
    import asyncio

    from textual.app import App
    from textual.widgets import Static

    from mailAgent.filingView import FilingEditor

    class EditorApp(App):
        def compose(self):
            yield FilingEditor()

    async def inspect():
        app = EditorApp()
        async with app.run_test(size=(100, 30)) as pilot:
            editor = app.query_one(FilingEditor)
            assert len(editor.query("#filing-disposition")) == 1
            assert len(editor.query("#filing-shortcuts")) == 1
            plan = {"parents": {"andy": ["Shopping"]}}
            editor.rowShow(None, plan)
            assert (
                str(editor.query_one("#filing-disposition", Static).render())
                == "Choose"
            )
            row = dict(domain="example.com", mailbox="andy", status="Needs choice")
            editor.rowShow(row, plan)
            assert (
                str(editor.query_one("#filing-disposition", Static).render())
                == "Choose"
            )
            for disposition in ("file", "ignore", "junk", "file"):
                editor.dispositionSet(disposition)
                await pilot.pause()
                assert (
                    str(editor.query_one("#filing-disposition", Static).render())
                    == disposition.title()
                )
                assert editor.query_one("#filing-parent-row").display == (
                    disposition == "file"
                )
                assert editor.query_one("#filing-folder-row").display == (
                    disposition == "file"
                )
                assert str(
                    editor.query_one("#filing-shortcuts", Static).render()
                ).startswith("i Ignore")
            calls = []
            monkeypatch.setattr(editor, "_ruleSave", calls.append)
            editor.action_sender_edit()
            editor.action_sender_edit()
            await pilot.pause()
            assert app.focused.id == "filing-sender"
            assert calls == [], "opening sender editing must never save"
            await pilot.press("enter")
            await pilot.pause()
            assert calls == ["sender"]

    asyncio.run(inspect())
