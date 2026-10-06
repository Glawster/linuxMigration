"""Digest reason policies keep personal mail prominent without changing mail."""

import asyncio

from mailAgent.interest import (
    interestEffective,
    interestLoad,
    interestReasonPolicies,
    interestReasonSet,
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


def testExplicitSenderIncludeOverridesReasonPolicy(tmp_path):
    path = tmp_path / "interesting.json"
    data = interestLoad(path)
    assert not interestEffective(data, "andy", "shop@example.com", "delivery")
    data = interestSet("andy", "shop@example.com", True, path)
    assert interestEffective(data, "andy", "shop@example.com", "delivery")


def testLikelyPersonNeedsHumanDisplayNameAndNonAutomatedAddress():
    assert interestSuggest("andy.smith@example.com", [], "Andy Smith") == (True, "person")
    assert interestSuggest("support@example.com", [], "Andy Smith") == (False, "")
    assert interestSuggest("andy.smith@example.com", [], "Example Support Team") == (
        False,
        "",
    )
    assert interestSuggest("plain@example.com", [], "") == (False, "")


def testSubjectReasonTakesPrecedenceOverPerson():
    assert interestSuggest(
        "andy.smith@example.com", ["Your parcel delivery is tomorrow"], "Andy Smith"
    ) == (True, "delivery")


def testDigestReasonSubPanel(config, monkeypatch, tmp_path):
    from mailAgent import auditUi
    from textual.widgets import Button, DataTable, Select, TabPane, TabbedContent

    preference = tmp_path / "interesting.json"
    monkeypatch.setattr(auditUi, "interestLoad", lambda: interestLoad(preference))
    monkeypatch.setattr(
        auditUi,
        "interestReasonSet",
        lambda reason, policy: interestReasonSet(reason, policy, preference),
    )
    monkeypatch.setattr(
        auditUi,
        "interestSet",
        lambda mailbox, sender, included: interestSet(
            mailbox, sender, included, preference
        ),
    )

    snapshot = dict(mailboxes=[])

    async def uiInspect():
        app = auditUi.auditAppBuild(snapshot)
        async with app.run_test(size=(120, 40)):
            assert app.query_one("#digest-menu", TabbedContent)
            assert app.query_one("#digestSenders", TabPane)
            assert app.query_one("#digestReasons", TabPane)
            table = app.query_one("#digest-reason-table", DataTable)
            assert table.row_count >= 10
            assert app.query_one("#digest-reason-policy", Select)
            assert app.query_one("#digest-reason-apply", Button)

    asyncio.run(uiInspect())
