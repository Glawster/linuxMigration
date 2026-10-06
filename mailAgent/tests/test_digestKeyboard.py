"""Inbox Digest keyboard controls use consistent positive/negative directions."""

import asyncio

from mailAgent.interest import (
    interestLoad,
    interestPersonPolicyGet,
    interestPersonPolicySet,
    interestReasonPolicies,
    interestReasonSet,
    interestSenderPolicyGet,
    interestSenderPolicySet,
)


def testDigestKeyboardDirectionsAndSenderShortcuts(monkeypatch, tmp_path):
    from mailAgent import auditUi, interactiveAudit
    from textual.coordinate import Coordinate
    from textual.widgets import DataTable

    preference = tmp_path / "interesting.json"
    monkeypatch.setattr(auditUi, "interestLoad", lambda: interestLoad(preference))
    monkeypatch.setattr(
        auditUi,
        "interestReasonSet",
        lambda reason, policy: interestReasonSet(reason, policy, preference),
    )
    monkeypatch.setattr(
        auditUi,
        "interestSenderPolicySet",
        lambda mailbox, sender, policy: interestSenderPolicySet(
            mailbox, sender, policy, preference
        ),
    )
    monkeypatch.setattr(
        auditUi,
        "interestPersonPolicySet",
        lambda mailbox, sender, policy: interestPersonPolicySet(
            mailbox, sender, policy, preference
        ),
    )

    snapshot = dict(
        mailboxes=[
            dict(
                id="andy",
                inboxInventory=dict(
                    messages=[
                        dict(
                            sender="friend@example.com",
                            senderName="Andy Smith",
                            subject="Hello",
                        )
                    ]
                ),
            )
        ]
    )

    async def uiInspect():
        app = interactiveAudit.auditAppBuild(snapshot)
        async with app.run_test(size=(120, 40)) as pilot:
            reasonTable = app.query_one("#digest-reason-table", DataTable)
            reasonTable.focus()
            reasonTable.cursor_coordinate = Coordinate(0, 1)

            # Right always moves toward the negative choice.
            await pilot.press("right")
            assert interestReasonPolicies(interestLoad(preference))["person"] == "manual"
            await pilot.press("right")
            assert interestReasonPolicies(interestLoad(preference))["person"] == "out"

            # Left always moves back toward the positive choice.
            await pilot.press("left")
            assert interestReasonPolicies(interestLoad(preference))["person"] == "manual"
            await pilot.press("left")
            assert interestReasonPolicies(interestLoad(preference))["person"] == "in"

            senderTable = app.query_one("#interest-table", DataTable)
            senderTable.focus()
            senderTable.cursor_coordinate = Coordinate(0, 1)

            await pilot.press("o")
            assert (
                interestSenderPolicyGet(
                    interestLoad(preference), "andy", "friend@example.com"
                )
                == "out"
            )
            await pilot.press("a")
            assert (
                interestSenderPolicyGet(
                    interestLoad(preference), "andy", "friend@example.com"
                )
                == "auto"
            )
            await pilot.press("i")
            assert (
                interestSenderPolicyGet(
                    interestLoad(preference), "andy", "friend@example.com"
                )
                == "in"
            )

            await pilot.press("n")
            assert (
                interestPersonPolicyGet(
                    interestLoad(preference), "andy", "friend@example.com"
                )
                == "no"
            )
            await pilot.press("y")
            assert (
                interestPersonPolicyGet(
                    interestLoad(preference), "andy", "friend@example.com"
                )
                == "yes"
            )

    asyncio.run(uiInspect())
