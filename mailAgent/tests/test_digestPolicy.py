"""Digest reason and sender policies keep personal mail prominent safely."""

import asyncio

from mailAgent.interest import (
    interestEffective,
    interestLoad,
    interestPersonPolicyGet,
    interestPersonPolicySet,
    interestReasonPolicies,
    interestReasonSet,
    interestSenderPolicyGet,
    interestSenderPolicySet,
    interestSet,
    interestSuggest,
)


def testDigestReasonDefaultsAndPersistence(tmp_path):
    path = tmp_path / "interesting.json"
    data = interestLoad(path)
    policies = interestReasonPolicies(data)
    assert policies["person"] == "in"
    assert policies["reminder"] == "in"
    assert policies["delivery"] == "out"
    assert policies["dispatch"] == "out"
    assert policies["order"] == "out"
    assert policies["payment"] == "out"
    assert policies["invoice"] == "out"
    assert policies["appointment"] == "manual"

    updated = interestReasonSet("delivery", "in", path)
    assert interestReasonPolicies(updated)["delivery"] == "in"
    assert interestReasonPolicies(interestLoad(path))["delivery"] == "in"
    assert path.stat().st_mode & 0o077 == 0


def testSenderPolicyCanOverrideIncludedReason(tmp_path):
    path = tmp_path / "interesting.json"
    data = interestLoad(path)
    assert interestEffective(data, "andy", "friend@example.com", "person")

    data = interestSenderPolicySet("andy", "friend@example.com", "out", path)
    assert interestSenderPolicyGet(data, "andy", "friend@example.com") == "out"
    assert not interestEffective(data, "andy", "friend@example.com", "person")

    data = interestSenderPolicySet("andy", "shop@example.com", "in", path)
    assert interestEffective(data, "andy", "shop@example.com", "delivery")

    data = interestSenderPolicySet("andy", "shop@example.com", "auto", path)
    assert not interestEffective(data, "andy", "shop@example.com", "delivery")


def testLegacyInterestSetRemainsCompatible(tmp_path):
    path = tmp_path / "interesting.json"
    data = interestSet("andy", "friend@example.com", True, path)
    assert interestSenderPolicyGet(data, "andy", "friend@example.com") == "in"
    data = interestSet("andy", "friend@example.com", False, path)
    assert interestSenderPolicyGet(data, "andy", "friend@example.com") == "auto"


def testPersonOverrideCorrectsFalsePositiveAndNegative(tmp_path):
    path = tmp_path / "interesting.json"
    data = interestLoad(path)
    assert interestPersonPolicyGet(data, "andy", "person@example.com") == "auto"

    data = interestPersonPolicySet("andy", "person@example.com", "no", path)
    assert interestPersonPolicyGet(data, "andy", "person@example.com") == "no"
    assert interestSuggest("person@example.com", [], "Andy Smith", "no") == (False, "")

    data = interestPersonPolicySet("andy", "plain@example.com", "yes", path)
    assert interestPersonPolicyGet(data, "andy", "plain@example.com") == "yes"
    assert interestSuggest("plain@example.com", [], "", "yes") == (True, "person")

    data = interestPersonPolicySet("andy", "plain@example.com", "auto", path)
    assert interestPersonPolicyGet(data, "andy", "plain@example.com") == "auto"


def testLikelyPersonNeedsHumanDisplayNameAndNonAutomatedAddress():
    assert interestSuggest("andy.smith@example.com", [], "Andy Smith") == (True, "person")
    assert interestSuggest("support@example.com", [], "Andy Smith") == (False, "")
    assert interestSuggest("andy.smith@example.com", [], "Example Support Team") == (
        False,
        "",
    )
    assert interestSuggest("plain@example.com", [], "") == (False, "")


def testSubjectReasonTakesPrecedenceOverPersonOverride():
    assert interestSuggest(
        "andy.smith@example.com",
        ["Your parcel delivery is tomorrow"],
        "Andy Smith",
        "no",
    ) == (True, "delivery")


def testDigestSubPanelsUseDirectEditableTables(monkeypatch, tmp_path):
    from mailAgent import auditUi, interactiveAudit
    from textual.coordinate import Coordinate
    from textual.widgets import DataTable, TabPane, TabbedContent

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
            assert app.query_one("#digest-menu", TabbedContent)
            assert app.query_one("#digestSenders", TabPane)
            assert app.query_one("#digestReasons", TabPane)

            reasonTable = app.query_one("#digest-reason-table", DataTable)
            assert reasonTable.row_count >= 10
            assert len(app.query("#digest-reason-policy")) == 0
            assert len(app.query("#digest-reason-apply")) == 0

            reasonTable.focus()
            reasonTable.cursor_coordinate = Coordinate(0, 1)
            await pilot.press("right")
            assert interestReasonPolicies(interestLoad(preference))["person"] == "manual"
            await pilot.press("left")
            assert interestReasonPolicies(interestLoad(preference))["person"] == "in"

            senderTable = app.query_one("#interest-table", DataTable)
            senderTable.focus()
            senderTable.cursor_coordinate = Coordinate(0, 5)
            await pilot.press("left")
            assert (
                interestSenderPolicyGet(
                    interestLoad(preference), "andy", "friend@example.com"
                )
                == "in"
            )
            await pilot.press("right")
            assert (
                interestSenderPolicyGet(
                    interestLoad(preference), "andy", "friend@example.com"
                )
                == "auto"
            )

            senderTable.cursor_coordinate = Coordinate(0, 6)
            await pilot.press("left")
            assert (
                interestPersonPolicyGet(
                    interestLoad(preference), "andy", "friend@example.com"
                )
                == "yes"
            )
            await pilot.press("right")
            assert (
                interestPersonPolicyGet(
                    interestLoad(preference), "andy", "friend@example.com"
                )
                == "auto"
            )

    asyncio.run(uiInspect())
