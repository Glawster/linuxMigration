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
    filingDomainClarify,
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


def testPublicSuffixListCoversLessObviousBoundaries():
    assert filingDomainExtract("orders@amazon.com.au") == "amazon.com.au"
    assert filingDomainExtract("news@bbc.co.uk") == "bbc.co.uk"
    assert filingDomainExtract("shop@example.com.br") == "example.com.br"
    assert filingDomainExtract("office@city.kawasaki.jp") == "city.kawasaki.jp"
    assert filingDomainExtract("hello@www.x.kawasaki.jp") == "www.x.kawasaki.jp"
    assert filingDomainExtract("admin@school.pvt.k12.wy.us") == "pvt.k12.wy.us"
    assert filingDomainExtract("support@telinet.com.pg") == "telinet.com.pg"
    assert filingDomainExtract("reader@foo.blogspot.com") is None
    assert filingDomainExtract("pages@name.github.io") is None
    assert filingDomainExtract("alerts@notifications.service.gov.uk") is None
    assert filingDomainExtract("person@co.uk") is None
    assert filingDomainExtract("person@com") is None


def testUncertainDomainAsksForClarification(world, tmp_path):
    rulesPath = tmp_path / "filing-rules.json"
    for bare in ("co.uk", "com", "com.au", "mail.amazon.co.uk"):
        with pytest.raises(ValueError):
            filingDomainSet("andy", bare, "Finance", "PayPal", False, rulesPath)
    with pytest.raises(ValueError):
        filingDomainClarify("andy", "amazon.co.uk", "amazon.com", rulesPath)

    snapshot = _snapshot(world)
    snapshot["mailboxes"][0]["inboxInventory"]["messages"] = [
        _message("nhs", "ask@nhs.uk", 2026, True),
        _message("blog", "reader@foo.blogspot.com", 2026, True),
        _message("pages", "pages@name.github.io", 2025, True),
    ]
    context = filingContextBuild(world["config"])
    plan = filingPlanBuild(context, snapshot, filingRulesLoad(rulesPath))
    assert not any(
        item["source"]["uid"] in {"nhs", "blog", "pages"} for item in plan["proposals"]
    )
    rows = {row["domain"]: row for row in plan["rows"]}
    assert rows["nhs.uk"]["status"] == "Needs choice"
    assert rows["nhs.uk"]["domainUncertain"] is True
    assert rows["foo.blogspot.com"]["domainUncertain"] is True
    assert rows["name.github.io"]["domainUncertain"] is True
    assert {
        review["source"].get("sender")
        for review in plan["reviews"]
        if review["reason"] == "Domain needs clarification"
    } == {
        "ask@nhs.uk",
        "reader@foo.blogspot.com",
        "pages@name.github.io",
    }
    assert not (world["andy"] / "Medical").exists()

    filingDomainSet("andy", "nhs.uk", "Medical", "NHS", True, rulesPath)
    confirmed = filingPlanBuild(context, snapshot, filingRulesLoad(rulesPath))
    nhs = _proposal(confirmed["proposals"], "andy", "nhs")
    assert nhs["decisionSource"] == "domain"
    assert nhs["canonical"] == "Medical/NHS"
    assert nhs["source"]["domain"] == "nhs.uk"
    assert nhs["executionPermitted"] is False
    assert nhs["sourceRemovalAllowed"] is False
    assert not any(
        review["source"].get("sender") == "ask@nhs.uk"
        for review in confirmed["reviews"]
    )
    assert not (world["andy"] / "Medical").exists()

    filingDomainClarify("andy", "foo.blogspot.com", "blogspot.com", rulesPath)
    filingDomainSet("andy", "blogspot.com", "Shopping", "Amazon", False, rulesPath)
    clarified = filingPlanBuild(context, snapshot, filingRulesLoad(rulesPath))
    blog = _proposal(clarified["proposals"], "andy", "blog")
    assert blog["source"]["domain"] == "blogspot.com"
    assert blog["canonical"] == "Shopping/Amazon"
    assert blog["executionPermitted"] is False
    assert not any(row["domain"] == "foo.blogspot.com" for row in clarified["rows"])
    blogRow = next(row for row in clarified["rows"] if row["domain"] == "blogspot.com")
    assert blogRow["domainUncertain"] is False
    assert any(
        review["source"].get("sender") == "pages@name.github.io"
        and review["reason"] == "Domain needs clarification"
        for review in clarified["reviews"]
    )


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
        review["reason"] == "Domain needs clarification"
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
        _message("guess", "notice@paypal-status.com", 2026, True)
    ]
    plan = filingPlanBuild(
        context, snapshot, filingRulesLoad(world["root"] / "none.json")
    )
    assert plan["proposals"] == []
    row = next(item for item in plan["rows"] if item["domain"] == "paypal-status.com")
    assert row["status"] == "Needs choice"
    assert any(
        review["source"].get("sender") == "notice@paypal-status.com"
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


def testAuditScreenUsesSharedStylesheet():
    from importlib.resources import files
    from pathlib import Path, PurePath

    from mailAgent.auditUi import auditAppBuild
    from textual.css.stylesheet import Stylesheet

    source = files("organiseMyProjects").joinpath("myStyles.css")
    app = auditAppBuild(
        {
            "schemaVersion": 1,
            "mailboxes": [],
            "localArchives": [],
            "sources": [],
        }
    )
    assert isinstance(app.CSS_PATH, PurePath)
    assert Path(app.CSS_PATH) == Path(source)
    assert app.css_path == [Path(source)]
    sheet = Stylesheet()
    sheet.read(app.css_path[0])
    sheet.parse()


def testAuditTableTextStaysOnDarkSurface():
    from textual.widgets import DataTable

    from mailAgent.auditUi import auditAppBuild

    snapshot = {
        "schemaVersion": 1,
        "mailboxes": [],
        "localArchives": [],
        "sources": [],
    }

    async def inspect() -> None:
        app = auditAppBuild(snapshot)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            table = app.query_one("#folders-table", DataTable)
            background = table.styles.background
            colour = table.styles.color
            assert background.a == 1
            assert (background.r + background.g + background.b) / 3 < 80
            assert (colour.r + colour.g + colour.b) / 3 > 180

    asyncio.run(inspect())


def testFooterKeysUseHeadingColour():
    from textual.widgets import Static

    from mailAgent.auditUi import auditAppBuild

    snapshot = {
        "schemaVersion": 1,
        "mailboxes": [],
        "localArchives": [],
        "sources": [],
    }

    async def inspect() -> None:
        app = auditAppBuild(snapshot)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            heading = app.query_one("#safety", Static).styles.color
            keys = list(app.query("FooterKey"))
            descriptions = {key.description.casefold() for key in keys}
            assert "quit" in descriptions
            assert "palette" in descriptions
            for key in keys:
                for name in ("footer-key--key", "footer-key--description"):
                    colour = key.get_component_rich_style(name).color
                    assert colour is not None
                    assert (
                        colour.triplet.red,
                        colour.triplet.green,
                        colour.triplet.blue,
                    ) == (
                        heading.r,
                        heading.g,
                        heading.b,
                    )

    asyncio.run(inspect())


def testFilingColumnsClipAndFit():
    from mailAgent.filingView import _columnWidths, _textClip

    assert _textClip("Shopping/Dunnes", 8) == "Shoppin…"
    assert _textClip("Amazon", 8) == "Amazon"
    widths = _columnWidths(120, 1)
    assert widths["domain"] > widths["destination"]
    assert widths["destination"] >= 8
    assert sum(widths.values()) + 2 * len(widths) <= 120
    narrow = _columnWidths(70, 1)
    assert sum(narrow.values()) + 2 * len(narrow) <= 70


def _coloursContrast(foreground, background) -> None:
    """Fail when text and its surface are too close to tell apart."""
    assert background.a == 1
    assert (
        abs(
            (foreground.r + foreground.g + foreground.b) / 3
            - (background.r + background.g + background.b) / 3
        )
        > 80
    )


def _screenText(app) -> str:
    """Return the text currently painted on the audit screen."""
    import io

    from rich.console import Console

    console = Console(
        width=app.size.width,
        height=app.size.height,
        file=io.StringIO(),
        force_terminal=True,
        record=True,
        color_system="truecolor",
    )
    painted = app.screen._compositor.render_update(
        full=True, screen_stack=app.app._background_screens
    )
    console.print(painted)
    return console.export_text()


def testFilingPanelCanProposeParentWithoutCreatingFolder(world, tmp_path, monkeypatch):
    from mailAgent.auditUi import auditAppBuild
    from mailAgent.filingView import FilingEditor, FilingView
    from textual.widgets import (
        Button,
        DataTable,
        Input,
        Select,
        Static,
        TabbedContent,
        TabPane,
    )

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
            moving = app.query_one("#inboxFiling", TabPane)
            assert str(moving._title) == "Moving Mail"
            assert all(
                pane.id != "inboxFiling"
                for pane in app.query_one("#digest-menu", TabbedContent).query(TabPane)
            )
            app.query_one(TabbedContent).active = "inboxFiling"
            await pilot.pause()
            table = app.query_one("#filing-table", DataTable)
            assert table.row_count >= 1
            summary = str(app.query_one("#filing-summary", Static).render())
            assert summary == (
                "Read mail may be filed. "
                "No folders or mail are changed in this phase."
            )
            view = app.query_one(FilingView)
            editor = app.query_one(FilingEditor)
            actions = [
                app.query_one("#filing-add-parent", Button),
                app.query_one("#filing-save-domain", Button),
                app.query_one("#filing-save-sender", Button),
            ]
            assert all("filing-action" in button.classes for button in actions)
            assert len({button.size.width for button in actions}) == 1
            assert len({button.size.height for button in actions}) == 1
            assert all(button.region.bottom <= app.size.height for button in actions)
            assert table.size.height > editor.size.height
            assert table.size.height * 10 >= view.size.height * 6
            assert 0 < table.virtual_size.width <= table.scrollable_content_region.width

            amazonRow = next(
                index
                for index in range(table.row_count)
                if "amazon.co.uk" in str(table.get_row_at(index))
            )
            table.move_cursor(row=amazonRow)
            await pilot.pause()
            assert app.query_one("#filing-domain-row").display is False
            assert "amazon.co.uk" in str(
                app.query_one("#filing-heading", Static).render()
            )
            assert app.query_one("#filing-sender-row").display is False

            nhsRow = next(
                index
                for index in range(table.row_count)
                if "nhs.uk" in str(table.get_row_at(index))
            )
            table.move_cursor(row=nhsRow)
            await pilot.pause()
            heading = str(app.query_one("#filing-heading", Static).render())
            assert heading.startswith("Filing:")
            assert "nhs.uk" in heading
            assert app.query_one("#filing-domain-row").display is True
            assert "Needs choice" in str(
                app.query_one("#filing-row-status", Static).render()
            )
            assert app.query_one("#filing-sender-row").display is False
            parent = app.query_one("#filing-parent", Select)
            child = app.query_one("#filing-child", Input)
            assert parent.region.y == child.region.y
            assert parent.content_region.height == 1
            assert child.content_region.height == 1
            assert child.styles.border
            assert child.value.strip()
            _coloursContrast(child.styles.color, child.styles.background)
            label = parent.query_one("#label", Static)
            current = parent.query_one("SelectCurrent")
            _coloursContrast(label.styles.color, current.styles.background)
            assert str(label.render()).strip()
            for button in actions:
                assert button.content_region.height == 1
                assert button.styles.border
                assert str(button.label).strip()
                _coloursContrast(button.styles.color, button.styles.background)
            painted = _screenText(app)
            assert "Add parent" in painted
            assert "Save domain" in painted
            assert "Sender override" in painted
            assert child.value in painted
            assert "▼" in painted

            app.query_one("#filing-save-sender", Button).focus()
            await pilot.press("enter")
            await pilot.pause()
            assert app.query_one("#filing-sender-row").display is True
            assert all(button.region.bottom <= app.size.height for button in actions)

            app.query_one("#filing-add-parent", Button).focus()
            await pilot.press("enter")
            await pilot.pause()
            name = app.query_one("#filing-parent-name", Input)
            assert app.query_one("#filing-parent-name-row").display is True
            assert name.region.x == parent.region.x
            assert name.content_region.height == 1
            assert name.styles.border
            name.value = "Medical"
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


def testAuditScreenHidesConsoleFilingLog(monkeypatch):
    import io
    import logging
    from argparse import Namespace

    from organiseMyProjects.logUtils import getLogger, setApplication

    from mailAgent.cli import _interactiveShow

    setApplication("mailAgent")
    logger = getLogger(includeConsole=True)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.logger.addHandler(handler)

    def auditShow(snapshot, refresh):
        logger.done("inbox filing plan")
        return None

    monkeypatch.setattr("mailAgent.interactiveAudit.auditShow", auditShow)
    try:
        _interactiveShow(Namespace(), {}, {}, logger)
    finally:
        if handler in logger.logger.handlers:
            logger.logger.removeHandler(handler)

    assert "inbox filing plan" not in stream.getvalue()
    assert any(
        type(attached) is logging.StreamHandler for attached in logger.logger.handlers
    )


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


@pytest.mark.parametrize("disposition", ["ignore", "junk"])
def testDispositionsPersistOverrideHistoryAndNeverMove(world, tmp_path, disposition):
    from mailAgent.filing import filingDispositionSet

    path = tmp_path / "rules.json"
    filingDomainSet("andy", "amazon.co.uk", "Shopping", "Amazon", False, path)
    filingDispositionSet("andy", "domains", "amazon.co.uk", disposition, path)
    filingDispositionSet("andy", "senders", "service@paypal.com", disposition, path)
    filingSenderSet("andy", "news@amazon.co.uk", "Finance", "PayPal", False, path)
    snapshot = _snapshot(world)
    before = json.dumps(snapshot, sort_keys=True)
    archive = _tree(world["andy"])
    rules = filingRulesLoad(path)
    assert rules["mailboxes"]["andy"]["domains"]["amazon.co.uk"] == {
        "disposition": disposition
    }
    plan = filingPlanBuild(filingContextBuild(world["config"]), snapshot, rules)
    records = plan["dispositions"]
    assert records
    assert all(item["disposition"] == disposition for item in records)
    assert all(
        "destination" not in item and "canonical" not in item for item in records
    )
    assert all(
        not item["executionPermitted"] and not item["sourceRemovalAllowed"]
        for item in records
    )
    assert all(
        item["source"]["uid"] not in ("unread", "unknown", "outside")
        for item in records
    )
    assert (
        _proposal(plan["proposals"], "andy", "reused-amazon")["decisionSource"]
        == "sender"
    )
    assert any(item["source"]["uid"] == "history-paypal" for item in records)
    row = next(
        row
        for row in plan["rows"]
        if row["mailbox"] == "andy" and row["domain"] == "amazon.co.uk"
    )
    assert row["status"] == disposition.title()
    assert row["canonical"] == row["parent"] == row["folder"] == ""
    assert json.dumps(snapshot, sort_keys=True) == before
    assert _tree(world["andy"]) == archive
    assert path.stat().st_mode & 0o077 == 0


@pytest.mark.parametrize(
    "decision",
    [
        {"disposition": "delete"},
        {"disposition": "ignore", "canonical": "Shopping/Amazon"},
        {"disposition": "junk", "parent": "Shopping"},
    ],
)
def testInvalidDispositionsRejected(tmp_path, decision):
    path = tmp_path / "rules.json"
    path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "mailboxes": {"andy": {"domains": {"amazon.co.uk": decision}}},
            }
        )
    )
    with pytest.raises(ValueError):
        filingRulesLoad(path)


@pytest.mark.parametrize("disposition", ["ignore", "junk"])
def testEditorSavesDispositionWithoutFolder(world, tmp_path, monkeypatch, disposition):
    from mailAgent.auditUi import auditAppBuild
    from textual.widgets import Button, DataTable, Select, TabbedContent

    path = tmp_path / "rules.json"
    monkeypatch.setattr("mailAgent.filing.filingPath", lambda: path)
    snapshot = _snapshot(world)
    snapshot["filingContext"] = filingContextBuild(world["config"])
    snapshot["filingPlan"] = filingPlanBuild(snapshot["filingContext"], snapshot)

    async def inspect():
        app = auditAppBuild(snapshot)
        async with app.run_test(size=(140, 42)) as pilot:
            app.query_one(TabbedContent).active = "inboxFiling"
            await pilot.pause()
            table = app.query_one("#filing-table", DataTable)
            index = next(
                i
                for i, row in enumerate(snapshot["filingPlan"]["rows"])
                if row["mailbox"] == "andy" and row["domain"] == "amazon.co.uk"
            )
            table.move_cursor(row=index)
            await pilot.pause()
            app.query_one("#filing-disposition", Select).value = disposition
            await pilot.pause()
            assert not app.query_one("#filing-choice-row").display
            await pilot.resize_terminal(110, 42)
            await pilot.pause()
            assert app.query_one("#filing-disposition", Select).value == disposition
            assert table.virtual_size.width <= table.scrollable_content_region.width
            app.query_one("#filing-save-domain", Button).press()
            await pilot.pause()
            assert filingRulesLoad(path)["mailboxes"]["andy"]["domains"][
                "amazon.co.uk"
            ] == {"disposition": disposition}

    asyncio.run(inspect())


@pytest.mark.parametrize("disposition", ["ignore", "junk"])
def testSenderDispositionWinsOverFileDomain(world, tmp_path, disposition):
    from mailAgent.filing import filingDispositionSet

    path = tmp_path / "rules.json"
    filingDomainSet("andy", "amazon.co.uk", "Shopping", "Amazon", False, path)
    filingDispositionSet("andy", "senders", "orders@amazon.co.uk", disposition, path)
    rules = filingRulesLoad(path)
    # Older Phase-1 File rules remain valid without an explicit disposition.
    rules["mailboxes"]["andy"]["domains"]["amazon.co.uk"].pop("disposition")
    plan = filingPlanBuild(filingContextBuild(world["config"]), _snapshot(world), rules)
    record = _proposal(plan["dispositions"], "andy", "live-amazon")
    assert record["decisionSource"] == "sender"
    assert record["disposition"] == disposition
    assert (
        _proposal(plan["proposals"], "andy", "reused-amazon")["disposition"] == "file"
    )
    assert not any(item["source"]["uid"] == "live-amazon" for item in plan["proposals"])
