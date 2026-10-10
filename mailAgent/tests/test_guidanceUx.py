"""Guidance UX remains explicit, read-only and easy to understand."""

from mailAgent.auditUi import _planActionText
from mailAgent.interest import interestSuggest
from mailAgent.migrationPlanning import _roleBoundary


def testRoleBoundaryDescribesEveryMailboxRole():
    assert _roleBoundary(dict(id="andy", role="personal")) == {
        "mailbox": "andy",
        "role": "personal",
        "reason": "Canonical local archive; live-year mail remains in personal IMAP",
    }
    assert (
        _roleBoundary(dict(id="old", role="legacy", migrationTarget="andy"))["reason"]
        == "Migrate into personal mailbox andy"
    )
    assert (
        "shared server taxonomy"
        in _roleBoundary(dict(id="hwfc", role="shared"))["reason"]
    )
    assert (
        "no personal archive migration"
        in _roleBoundary(dict(id="support", role="support"))["reason"]
    )


def testInboxDigestSuggestionsUseTransparentSubjectSignals():
    assert interestSuggest(
        "orders@example.com", ["Your order has been dispatched"]
    ) == (True, "dispatch")
    assert interestSuggest("hospital@example.com", ["Appointment reminder"]) == (
        True,
        "appointment",
    )
    assert interestSuggest("news@example.com", ["Weekly newsletter"]) == (False, "")


def testPlanActionTextPointsUserAtReviewQueue():
    plan = dict(reviewQueue=[{}, {}], proposals=[])
    assert _planActionText(plan) == (
        "⚠ ACTION NEEDED: 2 items need decisions — open Review Queue."
    )


def testPlanActionTextHighlightsMissingMirrorsAfterReview():
    plan = dict(
        reviewQueue=[],
        proposals=[
            dict(requiresFolderCreation=True),
            dict(requiresFolderCreation=False),
        ],
    )
    assert "review Proposed Moves" in _planActionText(plan)


def testPlanActionTextCanSayNothingIsRequired():
    assert _planActionText(dict(reviewQueue=[], proposals=[])).startswith("✓")


def testActionNeededGuidanceUsesWarningColourAndExplainsExecution():
    import asyncio

    from textual.widgets import Static

    from mailAgent.auditUi import auditAppBuild
    from mailAgent.filingView import _actionText, _tableCells

    rows = [
        dict(domain="example.com", status="Needs choice"),
        dict(domain="shop.example", status="Proposed child"),
    ]
    text = _actionText(rows)
    assert "edit its destination or press i/j" in text
    assert "review proposed folders" in text
    assert _actionText([dict(status="Existing")]) == ""
    assert _tableCells(rows[0], 16)[-1].style == "bold #f0c76a"

    async def inspect():
        app = auditAppBuild(dict(mailboxes=[], localArchives=[], sources=[]))
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            guidance = app.query_one("#plan-summary", Static)
            assert guidance.has_class("warning")
            assert (
                guidance.styles.color != app.query_one("#safety", Static).styles.color
            )
            assert "Execute is not available" in str(
                app.query_one("#safety", Static).render()
            )

    asyncio.run(inspect())


def testRightClickAndEnterNavigateToPlanControlsWithoutExecuting():
    import asyncio

    from textual.widgets import TabbedContent

    from mailAgent.auditUi import auditAppBuild

    async def inspect():
        for plan, target in (
            (None, "run-planning"),
            (
                dict(
                    reviewQueue=[dict(mailbox="andy", reason="Needs choice")],
                    proposals=[],
                    mappings=[],
                ),
                "review-table",
            ),
            (
                dict(
                    reviewQueue=[],
                    proposals=[
                        dict(
                            requiresFolderCreation=True,
                            action="file",
                            source=dict(mailbox="andy", folder="INBOX"),
                            destination=dict(
                                kind="imap", mailbox="andy", folder="Shopping"
                            ),
                            year=2026,
                        )
                    ],
                    mappings=[],
                ),
                "proposal-table",
            ),
        ):
            snapshot = dict(mailboxes=[], localArchives=[], sources=[])
            if plan is not None:
                snapshot["migrationPlan"] = plan
            app = auditAppBuild(snapshot)
            async with app.run_test(size=(120, 40)) as pilot:
                app.query_one(TabbedContent).active = "plan"
                await pilot.pause()
                selector = "#plan-summary" if plan is None else "#plan-action"
                await pilot.click(selector, button=3)
                await pilot.pause()
                assert app.focused.id == target
                if plan is not None:
                    app.query_one("#plan-menu", TabbedContent).active = "planSummary"
                    await pilot.pause()
                app.query_one(selector).focus()
                await pilot.press("enter")
                await pilot.pause()
                assert app.focused.id == target
                # Refresh is only focused: invoking it would exit the audit.
                assert app.is_running

    asyncio.run(inspect())


def testRightClickFilingGuidanceSelectsFirstNeededDecision():
    import asyncio

    from textual.widgets import DataTable, TabbedContent

    from mailAgent.auditUi import auditAppBuild

    rows = [
        dict(
            mailbox="andy", domain="done.example", status="Existing", disposition="file"
        ),
        dict(
            mailbox="andy",
            domain="choice.example",
            status="Needs choice",
            disposition="file",
        ),
    ]

    async def inspect():
        app = auditAppBuild(
            dict(mailboxes=[], localArchives=[], sources=[], filingPlan=dict(rows=rows))
        )
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one(TabbedContent).active = "inboxFiling"
            await pilot.pause()
            await pilot.click("#filing-summary", button=3)
            await pilot.pause()
            assert app.query_one("#filing-table", DataTable).cursor_row == 1
            assert app.focused.id == "filing-parent"
            from mailAgent.filingView import FilingView

            rows[1].update(status="Proposed child", decisionSource="domain")
            app.query_one(FilingView).planShow()
            await pilot.pause()
            assert not app.query_one("#filing-summary").has_class("action-needed")
            assert not app.query_one("#filing-row-status").has_class("warning")

    asyncio.run(inspect())
