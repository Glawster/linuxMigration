"""Read Inbox filing stays per-mailbox, reviewable and non-destructive."""

import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from organiseMyProjects.logUtils import setApplication

from mailAgent.archiveDiscovery import archiveDiscover
from mailAgent.configuration import configValidate
from mailAgent.filing import (
    filingChildSuggest,
    filingContextBuild,
    filingDomainExtract,
    filingDomainSet,
    filingNameNormalize,
    filingParentAdd,
    filingParentsDiscover,
    filingPlanBuild,
    filingRulesLoad,
    filingSenderSet,
)
from mailAgent.messageInventory import inboxMessagesDiscover, messageParse


@pytest.fixture
def world(tmp_path):
    setApplication("mailAgent")
    andy = _archiveCreate(tmp_path / "myMail")
    kathy = tmp_path / "kathyMail"
    kathy.mkdir()
    (kathy / "Family").write_bytes(b"")
    accounts = []
    for identity, role in (
        ("andy", "personal"),
        ("kathy", "personal"),
        ("old", "legacy"),
        ("hwfc", "shared"),
        ("clannEolas", "support"),
    ):
        account = dict(
            id=identity,
            name=identity,
            host=identity + ".example",
            username=identity,
            passwordEnv="MAIL_" + identity,
            role=role,
        )
        if identity == "andy":
            account["localArchive"] = str(andy)
        elif identity == "kathy":
            account["localArchive"] = str(kathy)
        elif role == "legacy":
            account["migrationTarget"] = "andy"
        accounts.append(account)
    config = configValidate(
        dict(general=dict(liveYear=2026), mailboxes=accounts), tmp_path
    )
    return dict(config=config, andy=andy, kathy=kathy, root=tmp_path)


def testRegistrableDomainsKeepCountryCodeSuffixes():
    assert filingDomainExtract("billing@bmw.com") == "bmw.com"
    assert filingDomainExtract("service@paypal.com") == "paypal.com"
    assert filingDomainExtract("orders@amazon.co.uk") == "amazon.co.uk"
    assert filingDomainExtract("orders@mail.amazon.co.uk") == "amazon.co.uk"
    assert filingDomainExtract("orders@amazon.com") == "amazon.com"
    assert (
        filingDomainExtract(
            "barclaycard_at_emails_barclaycard_co_uk_"
            "jvbcnca1d60ftp_cbn55768@icloud.com"
        )
        == "barclaycard.co.uk"
    )
    assert filingDomainExtract("not-an-address") is None


def testChildSuggestionAndFirstLevelParents(world):
    assert filingChildSuggest("bmw.com") == "BMW"
    assert filingChildSuggest("nhs.uk") == "NHS"
    assert filingChildSuggest("amazon.co.uk") == "Amazon"
    assert filingChildSuggest("paypal.com") == "PayPal"
    archive = archiveDiscover(world["andy"])
    assert filingChildSuggest("paypal.com", archive["folders"]) == "PayPal"
    assert filingParentsDiscover(archive) == ["Finance", "Shopping"]
    assert "Amazon" not in filingParentsDiscover(archive)
    assert "PayPal" not in filingParentsDiscover(archive)
    assert filingParentsDiscover(archiveDiscover(world["kathy"])) == ["Family"]


@pytest.mark.parametrize(
    "name",
    ["", "   ", ".", "..", ".hidden", "Orders/Shop", "Orders\\Shop", "Shop.sbd"],
)
def testFolderNamesRejectUnsafeComponents(name):
    with pytest.raises(ValueError):
        filingNameNormalize(name)


def testReadInboxPlanIsScopedTraceableAndDoesNotMutate(world, tmp_path):
    rulesPath = tmp_path / "filing-rules.json"
    before = _tree(world["andy"])
    filters = tmp_path / "msgFilterRules.dat"
    filters.write_text("existing thunderbird filters\n")
    filingParentAdd("andy", "Medical", rulesPath)
    filingDomainSet("andy", "amazon.co.uk", "Shopping", "Amazon", False, rulesPath)
    filingDomainSet("andy", "bmw.com", "Cars", "BMW", True, rulesPath)
    filingSenderSet("andy", "special@bmw.com", "Finance", "PayPal", False, rulesPath)
    context = filingContextBuild(world["config"])
    snapshot = _snapshot(world)
    plan = filingPlanBuild(context, snapshot, filingRulesLoad(rulesPath))
    again = filingPlanBuild(context, snapshot, filingRulesLoad(rulesPath))

    assert plan == again
    assert plan["executionEnabled"] is False
    assert before == _tree(world["andy"])
    assert not (world["andy"] / "Cars").exists()
    assert not (world["andy"] / "Cars.sbd").exists()
    assert not (world["andy"] / "Medical").exists()
    assert filters.read_text() == "existing thunderbird filters\n"
    assert rulesPath.stat().st_mode & 0o077 == 0
    stored = rulesPath.read_text()
    assert "password" not in stored.lower()
    assert "subject" not in stored.lower()

    rows = {(row["archive"], row["domain"]): row for row in plan["rows"]}
    amazon = rows[("myMail", "amazon.co.uk")]
    assert amazon["inboxCount"] == 6
    assert amazon["parent"] == "Shopping"
    assert amazon["folder"] == "Amazon"
    assert amazon["status"] == "Existing"
    assert rows[("myMail", "bmw.com")]["status"] == "Proposed parent + child"
    assert rows[("myMail", "nhs.uk")]["status"] == "Needs choice"
    assert rows[("kathyMail", "amazon.co.uk")]["status"] == "Needs choice"
    assert rows[("kathyMail", "amazon.co.uk")]["canonical"] == ""
    assert "Finance" not in filingParentsDiscover(archiveDiscover(world["kathy"]))

    proposals = plan["proposals"]
    assert all(item["executionPermitted"] is False for item in proposals)
    assert all(item["sourceRemovalAllowed"] is False for item in proposals)
    assert all(item["source"]["seen"] is True for item in proposals)
    assert all(item["readState"] == "read" for item in proposals)
    assert {item["source"]["folder"] for item in proposals} == {"INBOX"}
    assert not any(
        item["source"]["uid"] in {"unread", "outside", "unknown"} for item in proposals
    )
    assert not any(
        item["source"]["mailbox"] in {"hwfc", "clannEolas"} for item in proposals
    )

    live = _proposal(proposals, "andy", "live-amazon")
    assert live["destination"]["kind"] == "imap"
    assert live["destination"]["mailbox"] == "andy"
    assert live["destination"]["folder"] == "Shopping.Amazon"
    assert live["requiresFolderCreation"] is False
    assert live["decisionSource"] == "domain"
    assert live["canonical"] == "Shopping/Amazon"

    older = _proposal(proposals, "andy", "old-amazon")
    assert older["destination"]["kind"] == "local"
    assert older["destination"]["folder"] == "Shopping/Amazon"
    assert older["destination"]["path"].endswith("/Shopping.sbd/Amazon")
    assert older["removalPolicy"] == "copy-verify-remove"
    assert older["requiresFolderCreation"] is False

    reused = _proposal(proposals, "andy", "reused-amazon")
    assert reused["decisionSource"] == "domain"
    assert reused["canonical"] == "Shopping/Amazon"

    override = _proposal(proposals, "andy", "override-bmw")
    assert override["decisionSource"] == "sender"
    assert override["canonical"] == "Finance/PayPal"
    assert "Archive history" not in override["evidence"]

    proposed = _proposal(proposals, "andy", "proposed-bmw")
    assert proposed["decisionSource"] == "domain"
    assert proposed["canonical"] == "Cars/BMW"
    assert proposed["requiresFolderCreation"] is True
    assert proposed["destination"]["kind"] == "imap"
    assert proposed["destination"]["exists"] is False

    legacy = _proposal(proposals, "old", "legacy-amazon")
    assert legacy["destination"]["mailbox"] == "andy"
    assert legacy["destination"]["kind"] == "local"
    assert legacy["removalPolicy"] == "copy-verify-remove"
    assert legacy["sourceRemovalAllowed"] is False

    history = _proposal(proposals, "andy", "history-paypal")
    assert history["decisionSource"] == "archive history"
    assert history["canonical"] == "Finance/PayPal"
    assert "service@paypal.com" in history["evidence"]
    assert history["destination"]["kind"] == "imap"

    assert any(
        review["reason"] == "No safe canonical destination"
        and review["source"].get("sender") == "ask@nhs.uk"
        for review in plan["reviews"]
    )
    assert not any(
        review["source"].get("uid") == "unread" for review in plan["reviews"]
    )
    assert {item["mailbox"] for item in plan["excluded"]} == {"hwfc", "clannEolas"}
    assert any(item["sender"] == "special@bmw.com" for item in plan["senderOverrides"])
    assert "Medical" in plan["proposedParents"]["andy"]


def testUnsafeArchiveHistoryStaysInReview(world):
    context = filingContextBuild(world["config"])
    snapshot = _snapshot(world)
    snapshot["mailboxes"][0]["inboxInventory"]["messages"] = [
        _message("guess", "notice@paypal-status.example", 2026, True)
    ]
    plan = filingPlanBuild(
        context, snapshot, filingRulesLoad(world["root"] / "none.json")
    )
    assert plan["proposals"] == []
    row = next(
        item for item in plan["rows"] if item["domain"] == "paypal-status.example"
    )
    assert row["status"] == "Needs choice"
    assert any(
        review["source"].get("sender") == "notice@paypal-status.example"
        and review["reason"] == "No safe canonical destination"
        for review in plan["reviews"]
    )


def testOlderProposedMailKeepsSourceUntilVerified(world, tmp_path):
    rulesPath = tmp_path / "filing-rules.json"
    filingDomainSet("andy", "bmw.com", "Cars", "BMW", True, rulesPath)
    snapshot = _snapshot(world)
    snapshot["mailboxes"][0]["inboxInventory"]["messages"] = [
        _message("old-bmw", "service@bmw.com", 2024, True)
    ]
    plan = filingPlanBuild(
        filingContextBuild(world["config"]), snapshot, filingRulesLoad(rulesPath)
    )
    proposal = plan["proposals"][0]
    assert proposal["destination"]["kind"] == "local"
    assert proposal["destination"]["path"] is None
    assert proposal["requiresFolderCreation"] is True
    assert proposal["removalPolicy"] == "copy-verify-remove"
    assert proposal["sourceRemovalAllowed"] is False
    assert proposal["executionPermitted"] is False
    assert not (world["andy"] / "Cars").exists()
    assert not (world["andy"] / "Cars.sbd").exists()


def testFilingRulesRejectSecretsAndBadSchema(tmp_path):
    path = tmp_path / "filing-rules.json"
    path.write_text(json.dumps({"schemaVersion": 2, "mailboxes": {}}))
    with pytest.raises(ValueError):
        filingRulesLoad(path)
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "mailboxes": {"andy": {"password": "secret", "domains": {}}},
            }
        )
    )
    with pytest.raises(ValueError):
        filingRulesLoad(path)


def testSeenFlagIsExplicitAndInboxFetchDoesNotStore():
    seen = messageParse(
        b"1 (UID 8 FLAGS (\\Seen \\Flagged))",
        b"Date: Thu, 1 Jan 2026 10:00:00 +0000\r\n",
        "INBOX",
        "42",
    )
    unseen = messageParse(
        b"1 (UID 8 FLAGS (\\Recent))",
        b"Date: Thu, 1 Jan 2026 10:00:00 +0000\r\n",
        "INBOX",
        "42",
    )
    unknown = messageParse(
        b"1 (UID 8)",
        b"Date: Thu, 1 Jan 2026 10:00:00 +0000\r\n",
        "INBOX",
        "42",
    )
    assert seen["seen"] is True
    assert unseen["seen"] is False
    assert unknown["seen"] is None

    client = Mock()
    client.select.return_value = ("OK", [b"1"])
    client.response.return_value = ("UIDVALIDITY", [b"42"])
    client.uid.side_effect = [
        ("OK", [b"7"]),
        (
            "OK",
            [
                (
                    b"1 (UID 7 FLAGS (\\Seen) BODY[HEADER.FIELDS (DATE FROM SUBJECT)] {64}",
                    b"Date: Thu, 1 Jan 2026 10:00:00 +0000\r\nFrom: a@bmw.com\r\n\r\n",
                ),
                b")",
            ],
        ),
    ]
    inventory = inboxMessagesDiscover(
        client, [dict(path="INBOX", delimiter=".", attributes=["\\Inbox"])]
    )
    assert inventory["messages"][0]["seen"] is True
    assert all(call.args[0] != "STORE" for call in client.uid.call_args_list)
    fetched = [
        call.args[2] for call in client.uid.call_args_list if call.args[0] == "FETCH"
    ]
    assert fetched == ["(UID FLAGS BODY.PEEK[HEADER.FIELDS (DATE FROM SUBJECT)])"]


def testAuditSnapshotCarriesDisabledFilingPlan(world, tmp_path, monkeypatch):
    from mailAgent import cli

    monkeypatch.setattr(
        "mailAgent.filing.filingRulesLoad",
        lambda path=None: {"schemaVersion": 1, "mailboxes": {}},
    )
    args = cli.parserBuild().parse_args([])
    args.state = tmp_path / "state"
    args.thunderbird = tmp_path / "thunderbird"
    snapshot = {
        "schemaVersion": 1,
        "mailboxes": _snapshot(world)["mailboxes"],
        "sources": [],
        "conflicts": [],
        "relationships": [],
    }
    monkeypatch.setattr(
        "mailAgent.discovery.discoveryRun",
        lambda *args, **kwargs: snapshot,
    )
    built = cli._snapshotBuild(args, world["config"], Mock())
    assert built["filingPlan"]["executionEnabled"] is False
    assert built["filingPlan"]["proposals"]
    assert all(
        proposal["executionPermitted"] is False
        for proposal in built["filingPlan"]["proposals"]
    )


def testFilingPanelCanProposeParentWithoutCreatingFolder(world, tmp_path, monkeypatch):
    from mailAgent.auditUi import auditAppBuild
    from textual.widgets import Button, DataTable, Input, Select, Static, TabbedContent

    rulesPath = tmp_path / "filing-rules.json"
    monkeypatch.setattr("mailAgent.filing.filingPath", lambda: rulesPath)
    context = filingContextBuild(world["config"])
    snapshot = _snapshot(world)
    snapshot["filingContext"] = context
    snapshot["filingPlan"] = filingPlanBuild(
        context, snapshot, filingRulesLoad(rulesPath)
    )
    before = _tree(world["andy"])

    async def uiInspect():
        app = auditAppBuild(snapshot)
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one(TabbedContent).active = "inboxInterest"
            await pilot.pause()
            app.query_one("#digest-menu", TabbedContent).active = "inboxFiling"
            await pilot.pause()
            table = app.query_one("#filing-table", DataTable)
            assert table.row_count >= 1
            nhsRow = next(
                index
                for index in range(table.row_count)
                if "nhs.uk" in str(table.get_row_at(index))
            )
            table.move_cursor(row=nhsRow)
            await pilot.pause()
            app.query_one("#filing-parent-name", Input).value = "Medical"
            app.query_one("#filing-add-parent", Button).focus()
            await pilot.press("enter")
            await pilot.pause()
            assert "No folder was created" in str(
                app.query_one("#filing-status", Static).render()
            )
            parent = app.query_one("#filing-parent", Select)
            parent.value = "Medical"
            app.query_one("#filing-child", Input).value = "NHS"
            app.query_one("#filing-save-domain", Button).focus()
            await pilot.press("enter")
            await pilot.pause()

    asyncio.run(uiInspect())
    assert before == _tree(world["andy"])
    assert not (world["andy"] / "Medical").exists()
    saved = filingRulesLoad(rulesPath)
    assert "Medical" in saved["mailboxes"]["andy"]["proposedParents"]
    assert saved["mailboxes"]["andy"]["domains"]["nhs.uk"]["canonical"] == "Medical/NHS"
    assert saved["mailboxes"]["andy"]["domains"]["nhs.uk"]["parentProposed"] is True


def _archiveCreate(root: Path) -> Path:
    root.mkdir()
    (root / "Shopping").write_bytes(b"")
    shopping = root / "Shopping.sbd"
    shopping.mkdir()
    (shopping / "Amazon").write_bytes(b"")
    finance = root / "Finance.sbd"
    finance.mkdir()
    (finance / "PayPal").write_bytes(
        b"From sender@example Tue Jan 1 00:00:00 2025\n"
        b"From: service@paypal.com\n"
        b"Subject: receipt\n\n"
        b"body\n"
    )
    return root


def _message(
    uid: str, sender: str, year: int | None, seen: bool | None, folder: str = "INBOX"
) -> dict:
    return dict(
        folder=folder,
        uid=uid,
        uidValidity="42",
        year=year,
        sender=sender,
        seen=seen,
    )


def _proposal(proposals: list, mailbox: str, uid: str) -> dict:
    return next(
        item
        for item in proposals
        if item["source"]["mailbox"] == mailbox and item["source"]["uid"] == uid
    )


def _snapshot(world: dict) -> dict:
    folders = [
        dict(path="INBOX", delimiter=".", attributes=["\\Inbox"]),
        dict(path="Shopping.Amazon", delimiter=".", attributes=[]),
        dict(path="Finance.PayPal", delimiter=".", attributes=[]),
    ]
    messages = {
        "andy": [
            _message("live-amazon", "orders@amazon.co.uk", 2026, True),
            _message("old-amazon", "orders@amazon.co.uk", 2025, True),
            _message("reused-amazon", "news@amazon.co.uk", 2026, True),
            _message("unread", "orders@amazon.co.uk", 2026, False),
            _message("outside", "orders@amazon.co.uk", 2026, True, "Archive"),
            _message("unknown", "orders@amazon.co.uk", 2026, None),
            _message("override-bmw", "special@bmw.com", 2026, True),
            _message("proposed-bmw", "service@bmw.com", 2026, True),
            _message("history-paypal", "service@paypal.com", 2026, True),
            _message("nhs", "ask@nhs.uk", 2026, True),
            _message("missing-year", "year@nhs.uk", None, True),
        ],
        "kathy": [_message("kathy-amazon", "orders@amazon.co.uk", 2026, True)],
        "old": [_message("legacy-amazon", "orders@amazon.co.uk", 2024, True)],
        "hwfc": [_message("shared", "orders@amazon.co.uk", 2026, True)],
        "clannEolas": [_message("support", "orders@amazon.co.uk", 2026, True)],
    }
    mailboxes = []
    for account in world["config"]["mailboxes"]:
        mailboxes.append(
            dict(
                id=account["id"],
                role=account["role"],
                folders=list(folders),
                inboxInventory=dict(
                    complete=True,
                    issues=[],
                    messages=messages[account["id"]],
                ),
            )
        )
    return dict(schemaVersion=1, mailboxes=mailboxes, localArchives=[], sources=[])


def _tree(root: Path) -> dict:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
