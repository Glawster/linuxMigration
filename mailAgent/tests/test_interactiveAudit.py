"""Interactive plan refresh stays inside the mounted Textual application."""

import asyncio

from textual.widgets import Button, DataTable, Static, TabbedContent

from mailAgent.interactiveAudit import auditAppBuild


def _planBuild(generated: str, sender: str) -> dict:
    proposal = dict(
        action="migrate",
        source=dict(
            mailbox="andy",
            folder="INBOX",
            uid="1",
            uidValidity="42",
            sender=sender,
        ),
        year=2026,
        destination=dict(
            kind="imap",
            mailbox="andy",
            folder="Finance.PayPal",
            exists=True,
        ),
        requiresFolderCreation=False,
        classification=dict(
            method="userSenderDecision",
            confidence="explicit",
            reason="User-selected canonical folder",
            evidenceCount=1,
        ),
    )
    return dict(
        schemaVersion=1,
        generatedAt=generated,
        liveYear=2026,
        executionEnabled=False,
        archives=[],
        mappings=[
            dict(
                mailbox="andy",
                canonical="Finance/PayPal",
                local="/archive/Finance/PayPal",
                localSelectable=True,
                imap="Finance.PayPal",
                imapExists=True,
                imapSelectable=True,
                label="Inferred",
            )
        ],
        proposals=[proposal],
        reviewQueue=[],
        excluded=[],
        summary=dict(
            messagesScanned=1,
            proposals=1,
            reviewItems=0,
            systemFolderMessagesExcluded=0,
            messagesWithInvalidDates=0,
            systemFoldersWithUnknownCounts=0,
        ),
    )


def _snapshotBuild(plan: dict) -> dict:
    return dict(
        schemaVersion=1,
        mailboxes=[],
        localArchives=[],
        sources=[],
        conflicts=[],
        changes=[],
        migrationPlan=plan,
    )


def testPlanRefreshKeepsTuiMountedAndUpdatesWidgets():
    snapshot = _snapshotBuild(_planBuild("2026-10-06T09:00:00+00:00", "old@example.com"))
    calls = []

    def refreshPlan():
        calls.append(True)
        return _snapshotBuild(
            _planBuild("2026-10-06T10:00:00+00:00", "new@example.com")
        )

    async def uiInspect():
        app = auditAppBuild(snapshot, refreshPlan)
        async with app.run_test(size=(120, 40)) as pilot:
            menu = app.query_one("#plan-menu", TabbedContent)
            menu.active = "planSummary"
            button = app.query_one("#refresh-planning", Button)
            button.focus()
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause()
                if calls and not button.disabled:
                    break

            assert calls == [True]
            assert app.return_value is None
            assert menu.active == "planSummary"
            assert "2026-10-06T10:00:00+00:00" in str(
                app.query_one("#plan-generated", Static).render()
            )
            table = app.query_one("#proposal-table", DataTable)
            assert table.row_count == 1
            assert "new@example.com" in str(table.get_row_at(0))
            assert snapshot["migrationPlan"]["generatedAt"] == (
                "2026-10-06T10:00:00+00:00"
            )

    asyncio.run(uiInspect())


def testPlanRefreshFailureKeepsExistingPlanVisible():
    snapshot = _snapshotBuild(_planBuild("2026-10-06T09:00:00+00:00", "old@example.com"))

    def refreshPlan():
        raise ValueError("scan unavailable")

    async def uiInspect():
        app = auditAppBuild(snapshot, refreshPlan)
        async with app.run_test(size=(120, 40)) as pilot:
            button = app.query_one("#refresh-planning", Button)
            button.focus()
            await pilot.press("enter")
            for _ in range(20):
                await pilot.pause()
                if not button.disabled:
                    break

            assert app.return_value is None
            assert "Plan refresh failed" in str(
                app.query_one("#plan-generated", Static).render()
            )
            assert snapshot["migrationPlan"]["generatedAt"] == (
                "2026-10-06T09:00:00+00:00"
            )

    asyncio.run(uiInspect())
