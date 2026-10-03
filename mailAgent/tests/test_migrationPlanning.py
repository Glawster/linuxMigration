"""Role boundaries, canonical taxonomy and read-only migration planning."""

import ast
import asyncio
import copy
import tomllib
from pathlib import Path
from unittest.mock import Mock

import pytest
from organiseMyProjects.logUtils import setApplication

from mailAgent.archiveClassification import archiveSenderIndex, senderClassify
from mailAgent.archiveDiscovery import archiveDiscover
from mailAgent.configuration import configValidate
from mailAgent.discovery import discoveryRun, snapshotSave
from mailAgent.interest import interestIs, interestLoad, interestSet
from mailAgent.messageInventory import inboxMessagesDiscover, messageParse, messagesDiscover
from mailAgent.migrationPlanning import folderMappingsBuild, migrationPlan
from mailAgent.planSummary import planSummaryLines
from mailAgent.senderAddress import senderRelayDecode


@pytest.fixture
def config(tmp_path):
    setApplication("mailAgent")
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
        if role == "personal":
            root = tmp_path / ("myMail" if identity == "andy" else "kathyMail")
            root.mkdir()
            (root / "Orders").write_bytes(
                b"From sender@example Tue Jan 1 00:00:00 2025\n\n"
            )
            (root / "Orders.sbd").mkdir()
            (root / "Orders.sbd/Shop").write_bytes(b"")
            account["localArchive"] = str(root)
        if role == "legacy":
            account["migrationTarget"] = "andy"
        accounts.append(account)
    return configValidate(
        dict(general=dict(liveYear=2026), mailboxes=accounts), tmp_path
    )


def snapshotBuild(config):
    mailboxes = []
    for account in config["mailboxes"]:
        mailboxes.append(
            dict(
                id=account["id"],
                name=account["name"],
                host=account["host"],
                username=account["username"],
                role=account["role"],
                folders=[
                    dict(path="Orders", delimiter="/", attributes=[]),
                    dict(path="Orders/Shop", delimiter="/", attributes=[]),
                ],
                quota=[],
                issues=[],
                inventory=dict(
                    complete=True,
                    issues=[],
                    messages=[
                        dict(
                            folder="Orders/Shop", uid="1", uidValidity="42", year=2026
                        ),
                        dict(
                            folder="Orders/Shop", uid="2", uidValidity="42", year=2025
                        ),
                    ],
                ),
            )
        )
    return dict(
        schemaVersion=1,
        mailboxes=mailboxes,
        sources=[],
        conflicts=[],
        relationships=[],
        changes=[],
    )


def inventoryClient():
    client = Mock()
    client.select.return_value = ("OK", [b"2"])
    client.response.return_value = ("UIDVALIDITY", [b"42"])
    client.uid.side_effect = [
        ("OK", [b"1 2"]),
        (
            "OK",
            [
                (
                    b"1 (UID 1 BODY[HEADER.FIELDS (DATE)] {38}",
                    b"Date: Thu, 1 Jan 2026 10:00:00 +0000\r\n\r\n",
                ),
                b")",
            ],
        ),
        (
            "OK",
            [
                (
                    b"2 (UID 2 BODY[HEADER.FIELDS (DATE)] {38}",
                    b"Date: Wed, 1 Jan 2025 10:00:00 +0000\r\n\r\n",
                ),
                b")",
            ],
        ),
    ]
    return client


def testConfigRolesAndHosts(config):
    assert len({a["host"] for a in config["mailboxes"]}) == 5
    assert (
        config["mailboxes"][2]["localArchive"] == config["mailboxes"][0]["localArchive"]
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("role", "unknown"),
        ("role", ""),
        ("port", 0),
        ("port", True),
        ("folderMappings", []),
        ("archiveFormat", "unknown"),
        ("localArchive", ""),
    ],
)
def testInvalidAccount(config, field, value):
    config["mailboxes"][0][field] = value
    with pytest.raises(ValueError):
        configValidate(config, Path.cwd())


@pytest.mark.parametrize("year", [True, "2026", 1800, 10000])
def testInvalidYear(config, year):
    config["general"]["liveYear"] = year
    with pytest.raises(ValueError):
        configValidate(config, Path.cwd())


def testInvalidLegacyTargetAndArchive(config):
    config["mailboxes"][2]["migrationTarget"] = "hwfc"
    with pytest.raises(ValueError):
        configValidate(config, Path.cwd())
    config["mailboxes"][2]["migrationTarget"] = "andy"
    config["mailboxes"][2]["localArchive"] = config["mailboxes"][1]["localArchive"]
    with pytest.raises(ValueError):
        configValidate(config, Path.cwd())


@pytest.mark.parametrize("identity", ["hwfc", "clannEolas"])
def testNoPersonalSettingsOnOtherRoles(config, identity):
    next(a for a in config["mailboxes"] if a["id"] == identity)[
        "localArchive"
    ] = "/not/personal"
    with pytest.raises(ValueError):
        configValidate(config, Path.cwd())


def testRelativeRoot(config, tmp_path):
    config["mailboxes"][0]["localArchive"] = "relative/myMail"
    config["mailboxes"][2].pop("localArchive")
    normalized = configValidate(config, tmp_path)
    assert normalized["mailboxes"][0]["localArchive"] == str(
        tmp_path / "relative/myMail"
    )
    assert not (tmp_path / "relative").exists()
    assert config["mailboxes"][0]["localArchive"] == "relative/myMail"


def testExampleConfiguration():
    project = Path(__file__).parents[1]
    parsed = configValidate(
        tomllib.loads((project / "config.example.toml").read_text()), project
    )
    assert len(parsed["mailboxes"]) == 5
    assert {a["role"] for a in parsed["mailboxes"]} == {
        "personal",
        "legacy",
        "shared",
        "support",
    }


def testThunderbirdTaxonomy(config):
    root = Path(config["mailboxes"][0]["localArchive"])
    (root / "Orders.msf").write_bytes(b"index")
    (root / "msgFilterRules.dat").write_bytes(b"not a folder")
    (root / "Parent.sbd").mkdir()
    (root / "Parent.sbd/Child").write_bytes(b"")
    (root / "unsupported").write_bytes(b"arbitrary data")
    archive = archiveDiscover(root)
    assert {f["path"] for f in archive["folders"]} == {
        "Orders",
        "Orders/Shop",
        "Parent",
        "Parent/Child",
    }
    assert (
        next(f for f in archive["folders"] if f["path"] == "Parent")["selectable"]
        is False
    )
    assert archive["issues"] == [
        "Unrecognized archive file: " + str(root / "unsupported")
    ]


def testMaildirAndSymlink(tmp_path):
    for folder in (tmp_path, tmp_path / "Orders"):
        for leaf in ("cur", "new", "tmp"):
            (folder / leaf).mkdir(parents=True)
    (tmp_path / "Orders/cur/message").write_bytes(b"Subject: private\n\nbody")
    (tmp_path / "link").symlink_to(tmp_path, target_is_directory=True)
    archive = archiveDiscover(tmp_path, "maildir")
    assert {f["path"] for f in archive["folders"]} == {"INBOX", "Orders"}
    assert len(archive["issues"]) == 1
    assert not archiveDiscover(tmp_path / "missing")["available"]
    assert not archiveDiscover(tmp_path / "link")["available"]
    with pytest.raises(ValueError):
        archiveDiscover(tmp_path, "unknown")


def testRoleBoundariesAndLiveYear(config):
    plan = migrationPlan(config, snapshotBuild(config))
    assert plan["executionEnabled"] is False
    assert {p["source"]["mailbox"] for p in plan["proposals"]} == {
        "andy",
        "kathy",
        "old",
    }
    assert {m["mailbox"] for m in plan["mappings"]} == {"andy", "kathy"}
    assert {e["mailbox"] for e in plan["excluded"]} == {"hwfc", "clannEolas"}
    for proposal in plan["proposals"]:
        assert proposal["destination"]["kind"] == (
            "imap" if proposal["year"] == 2026 else "local"
        )
        assert not proposal["sourceRemovalAllowed"]
    old = [p for p in plan["proposals"] if p["source"]["mailbox"] == "old"]
    assert {p["destination"]["mailbox"] for p in old} == {"andy"}
    assert next(p for p in old if p["year"] == 2025)["destination"]["path"].endswith(
        "myMail/Orders.sbd/Shop"
    )
    assert next(p for p in old if p["year"] == 2026)["action"] == "migrate"
    assert (
        next(
            p
            for p in plan["proposals"]
            if p["source"]["mailbox"] == "andy" and p["year"] == 2026
        )["action"]
        == "retain"
    )


def testCustomLiveYear(config):
    config["general"]["liveYear"] = 2027
    assert all(
        p["destination"]["kind"] == "local"
        for p in migrationPlan(config, snapshotBuild(config))["proposals"]
    )


def testFutureAndUnknownDatesReview(config):
    snapshot = snapshotBuild(config)
    messages = snapshot["mailboxes"][0]["inventory"]["messages"]
    messages[0]["year"], messages[1]["year"] = 2027, None
    plan = migrationPlan(config, snapshot)
    assert not any(p["source"]["mailbox"] == "andy" for p in plan["proposals"])
    assert len([r for r in plan["reviewQueue"] if r["mailbox"] == "andy"]) == 2


def testUnmatchedAndSystemFoldersReview(config):
    snapshot = snapshotBuild(config)
    mailbox = snapshot["mailboxes"][0]
    mailbox["folders"][1]["attributes"] = ["\\Trash"]
    assert any(
        "System folder" in r["reason"]
        for r in migrationPlan(config, snapshot)["reviewQueue"]
    )
    mailbox["folders"][1]["attributes"] = []
    mailbox["folders"][1]["path"] = "Unknown"
    mailbox["inventory"]["messages"][0]["folder"] = "Unknown"
    assert any(
        "canonical archive" in r["reason"]
        for r in migrationPlan(config, snapshot)["reviewQueue"]
    )


def testExplicitMappingsAndMirrors(config):
    snapshot = snapshotBuild(config)
    snapshot["mailboxes"][0]["folders"][1].update(
        path="INBOX.Orders.Shop", delimiter="."
    )
    config["mailboxes"][0]["folderMappings"] = {"INBOX.Orders.Shop": "Orders/Shop"}
    plan = migrationPlan(config, snapshot)
    mapping = next(
        m
        for m in plan["mappings"]
        if m["mailbox"] == "andy" and m["canonical"] == "Orders/Shop"
    )
    assert mapping["imap"] == "INBOX.Orders.Shop"
    snapshot["mailboxes"][0]["folders"] = [
        dict(path="INBOX", delimiter="/", attributes=[])
    ]
    plan = migrationPlan(config, snapshot)
    mapping = next(
        m
        for m in plan["mappings"]
        if m["mailbox"] == "andy" and m["canonical"] == "Orders/Shop"
    )
    assert mapping["mirrorProposed"]
    assert next(
        p
        for p in plan["proposals"]
        if p["source"]["mailbox"] == "old" and p["year"] == 2026
    )["requiresFolderCreation"]


def testMappingAmbiguityAndUnavailableTarget(config):
    snapshot = snapshotBuild(config)
    snapshot["mailboxes"][0]["folders"].append(
        dict(path="Other", delimiter="/", attributes=[])
    )
    config["mailboxes"][0]["folderMappings"] = {"Other": "Orders/Shop"}
    plan = migrationPlan(config, snapshot)
    assert any("Multiple server folders" in r["reason"] for r in plan["reviewQueue"])
    assert not any(
        p["source"]["mailbox"] == "old" and p["year"] == 2026 for p in plan["proposals"]
    )
    snapshot["mailboxes"][0]["failed"] = True
    plan = migrationPlan(config, snapshot)
    assert any("discovery unavailable" in r["reason"] for r in plan["reviewQueue"])
    assert not any(
        p["source"]["mailbox"] == "old" and p["year"] == 2026 for p in plan["proposals"]
    )


def testMissingArchiveAndInventory(config):
    config["mailboxes"][0]["localArchive"] += "-missing"
    config["mailboxes"][2].pop("localArchive")
    snapshot = snapshotBuild(config)
    snapshot["mailboxes"][1].pop("inventory")
    plan = migrationPlan(config, snapshot)
    assert not plan["proposals"]
    assert plan["reviewQueue"]


def testUnknownDelimiterAndUnicode(config):
    archive = dict(
        folders=[dict(path="Café", storage="/archive/Café", selectable=True)]
    )
    account = config["mailboxes"][0]
    mapping = folderMappingsBuild(
        account,
        dict(folders=[dict(path="INBOX", delimiter="/", attributes=[])]),
        archive,
    )[0]
    assert mapping["imap"] == "Caf&AOk-"
    observed = dict(folders=[dict(path="Caf&AOk-", delimiter="/", attributes=[])])
    assert folderMappingsBuild(account, observed, archive)[0]["imapExists"]
    observed["folders"][0].update(path="Other", delimiter=None)
    assert "issue" in folderMappingsBuild(account, observed, archive)[0]


def testPlanningNoMutation(config):
    snapshot = snapshotBuild(config)
    configBefore, snapshotBefore = copy.deepcopy(config), copy.deepcopy(snapshot)
    roots = [
        Path(a["localArchive"]) for a in config["mailboxes"] if a["role"] == "personal"
    ]
    files = {
        p: (p.read_bytes(), p.stat().st_mtime_ns)
        for root in roots
        for p in root.rglob("*")
        if p.is_file()
    }
    migrationPlan(config, snapshot)
    assert config == configBefore
    assert snapshot == snapshotBefore
    assert files == {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in files}


def testReadOnlyInventoryBatching():
    client = inventoryClient()
    inventory = messagesDiscover(
        client, [dict(path="Orders", attributes=[])], batchSize=1
    )
    assert inventory["complete"]
    assert [m["year"] for m in inventory["messages"]] == [2026, 2025]
    client.select.assert_called_once_with('"Orders"', readonly=True)
    assert {c[0] for c in client.mock_calls} == {"select", "response", "uid"}
    assert all(c.args[0] in ("SEARCH", "FETCH") for c in client.uid.call_args_list)
    assert all(
        "BODY.PEEK[HEADER.FIELDS (DATE FROM)]" in c.args[2]
        for c in client.uid.call_args_list
        if c.args[0] == "FETCH"
    )


@pytest.mark.parametrize(
    "header",
    [
        b"",
        b"Date: invalid\r\n",
        b"Date: Thu, 1 Jan 2026 10:00:00 +0000\r\nDate: Wed, 1 Jan 2025 10:00:00 +0000\r\n",
    ],
)
def testInvalidMessageDate(header):
    message = messageParse(b"1 (UID 8)", header, "Orders", "42")
    assert message["year"] is None
    assert message["issue"]
    with pytest.raises(ValueError):
        messageParse(b"1 ()", header, "Orders", "42")


@pytest.mark.parametrize(
    "failure", ["select", "validity", "search", "fetch", "missing", "duplicate"]
)
def testIncompleteInventory(failure):
    client = inventoryClient()
    if failure == "select":
        client.select.return_value = ("NO", [])
    elif failure == "validity":
        client.response.return_value = ("UIDVALIDITY", [None])
    elif failure == "search":
        client.uid.side_effect = [("NO", [])]
    elif failure == "fetch":
        client.uid.side_effect = [("OK", [b"1"]), ("NO", [])]
    elif failure == "missing":
        client.uid.side_effect = [("OK", [b"1"]), ("OK", [])]
    else:
        row = (b"1 (UID 1)", b"Date: Thu, 1 Jan 2026 10:00:00 +0000\r\n")
        client.uid.side_effect = [("OK", [b"1"]), ("OK", [row, row])]
    inventory = messagesDiscover(client, [dict(path="Orders", attributes=[])])
    assert not inventory["complete"]
    assert inventory["issues"]


def testNoSelectAndInvalidBatch():
    client = Mock()
    assert messagesDiscover(client, [dict(path="Parent", attributes=["\\Noselect"])])[
        "complete"
    ]
    assert not client.mock_calls
    with pytest.raises(ValueError):
        messagesDiscover(client, [], batchSize=0)


def testIncompleteInventoryNoProposals(config):
    snapshot = snapshotBuild(config)
    snapshot["mailboxes"][0]["inventory"].update(
        complete=False, issues=[dict(folder="Orders", message="Failed")]
    )
    plan = migrationPlan(config, snapshot)
    assert not any(p["source"]["mailbox"] == "andy" for p in plan["proposals"])
    assert any("Incomplete inventory" in r["reason"] for r in plan["reviewQueue"])


def testDiscoverySkipsSharedSupportInventory(config, tmp_path, monkeypatch):
    clients = []

    def clientFactory(host, port, timeout):
        client = inventoryClient()
        client.uid.side_effect = [
            ("OK", [b"1"]),
            ("OK", [(b"1 (UID 1)", b"Date: Thu, 1 Jan 2026 10:00:00 +0000\r\n")]),
        ]
        client.capabilities = (b"IMAP4rev1",)
        client.list.return_value = ("OK", [b'() "/" "Orders/Shop"'])
        client.status.return_value = ("OK", [b'"Orders/Shop" (MESSAGES 1 UNSEEN 0)'])
        clients.append(client)
        return client

    for account in config["mailboxes"]:
        monkeypatch.setenv(account["passwordEnv"], "secret-in-env")
    snapshot = discoveryRun(
        config["mailboxes"], tmp_path, clientFactory=clientFactory, includeMessages=True
    )
    assert all(c.select.called for c in clients[:3])
    assert all(not c.select.called for c in clients[3:])
    assert all(c.logout.called for c in clients)
    snapshot["migrationPlan"] = migrationPlan(config, snapshot)
    snapshotSave(snapshot, tmp_path / "state")
    assert "secret-in-env" not in (tmp_path / "state/latest.json").read_text()
    assert len(snapshot["mailboxes"]) == 5


def testCoreNoTextualDependency():
    root = Path(__file__).parents[1] / "src/mailAgent"
    for name in (
        "archiveClassification",
        "archiveDiscovery",
        "configuration",
        "messageInventory",
        "migrationPlanning",
        "interest",
        "planSummary",
    ):
        tree = ast.parse((root / (name + ".py")).read_text())
        imports = [
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        ]
        imports.extend(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        )
        assert not any(name and name.startswith("textual") for name in imports)


def testAuditPlanningViews(config):
    from mailAgent.auditUi import auditAppBuild
    from textual.widgets import Button, Static, TabPane, TabbedContent

    snapshot = snapshotBuild(config)
    snapshot["migrationPlan"] = migrationPlan(config, snapshot)

    async def uiInspect():
        app = auditAppBuild(snapshot)
        async with app.run_test(size=(120, 40)) as pilot:
            for identity in (
                "plan",
                "planSummary",
                "mappings",
                "proposals",
                "reviewQueue",
                "excluded",
            ):
                assert app.query_one("#" + identity, TabPane)
            assert len(app.query("#mailbox-3")) == 1
            assert len(app.query("#mailbox-4")) == 1
            assert len(app.query("#run-planning")) == 0
            planMenu = app.query_one("#plan-menu", TabbedContent)
            planMenu.active = "proposals"
            await pilot.pause()
            assert planMenu.active == "proposals"
            planMenu.active = "planSummary"
            await pilot.pause()
            assert "Messages scanned:" in str(
                app.query_one("#plan-summary", Static).render()
            )

    asyncio.run(uiInspect())


@pytest.mark.parametrize(
    "bad", [None, {}, {"general": []}, {"general": {}, "mailboxes": [None]}]
)
def testInvalidConfigurationShape(bad, tmp_path):
    with pytest.raises(ValueError):
        configValidate(bad, tmp_path)


def testAdditionalConfigurationGuards(config):
    for accountIndex, key, value in (
        (1, "id", "andy"),
        (0, "migrationTarget", "andy"),
        (2, "migrationTarget", []),
        (0, "localArchive", "bad\x00path"),
        (0, "folderMappings", {"Orders": "../escape"}),
        (0, "folderMappings", {"Orders": ""}),
    ):
        invalid = copy.deepcopy(config)
        invalid["mailboxes"][accountIndex][key] = value
        with pytest.raises(ValueError):
            configValidate(invalid, Path.cwd())


def testUnreadableArchive(config, monkeypatch):
    root = Path(config["mailboxes"][0]["localArchive"])
    monkeypatch.setattr(
        Path, "iterdir", lambda path: (_ for _ in ()).throw(PermissionError())
    )
    archive = archiveDiscover(root)
    assert archive["available"] and not archive["complete"]
    assert archive["issues"]


def testInvalidSearchResponse():
    client = inventoryClient()
    client.uid.side_effect = [("OK", [b"invalid-uid"])]
    assert not messagesDiscover(client, [dict(path="Orders", attributes=[])])[
        "complete"
    ]


def testUnsafeNamesAndMirrorCollision(config):
    archive = dict(
        folders=[dict(path="Orders", storage="/archive/Orders", selectable=True)]
    )
    account = config["mailboxes"][0]
    account["folderMappings"] = {"Orders": "Other"}
    assert (
        "collides"
        in folderMappingsBuild(
            account,
            dict(folders=[dict(path="Orders", delimiter="/", attributes=[])]),
            archive,
        )[0]["issue"]
    )
    for name, delimiter in (
        ("bad&encoding", "/"),
        ("Orders/Shop", "."),
        ("Orders//Shop", "/"),
    ):
        assert not folderMappingsBuild(
            account,
            dict(folders=[dict(path=name, delimiter=delimiter, attributes=[])]),
            archive,
        )[0]["imapExists"]
    account["folderMappings"] = {}
    archive["folders"][0]["path"] = "A&B"
    mapping = folderMappingsBuild(
        account,
        dict(folders=[dict(path="A&-B", delimiter="/", attributes=[])]),
        archive,
    )[0]
    assert mapping["imapExists"]


def testNonselectableDestinationsAndUnknownSource(config):
    snapshot = snapshotBuild(config)
    snapshot["mailboxes"][0]["folders"][1]["attributes"] = ["\\Noselect"]
    plan = migrationPlan(config, snapshot)
    assert not any(
        p["source"]["mailbox"] == "old" and p["year"] == 2026 for p in plan["proposals"]
    )
    assert any("cannot receive" in r["reason"] for r in plan["reviewQueue"])
    root = Path(config["mailboxes"][0]["localArchive"])
    (root / "Orders.sbd/Shop").unlink()
    (root / "Orders.sbd/Shop.sbd").mkdir()
    plan = migrationPlan(config, snapshot)
    assert any("no local message store" in r["reason"] for r in plan["reviewQueue"])
    snapshot["mailboxes"][0]["inventory"]["messages"][0]["folder"] = "Missing"
    assert any(
        "not observed" in r["reason"]
        for r in migrationPlan(config, snapshot)["reviewQueue"]
    )


@pytest.mark.parametrize("confirm", [False, True])
def testCliPlanningPersistenceBoundary(config, tmp_path, monkeypatch, confirm):
    from mailAgent import cli
    import mailAgent.discovery as discovery

    configPath = tmp_path / "config.toml"
    configPath.write_text(
        (Path(__file__).parents[1] / "config.example.toml").read_text()
    )
    monkeypatch.setattr(cli.tomllib, "loads", lambda text: config)
    snapshot = snapshotBuild(config)
    calls = []

    def scan(accounts, root, includeMessages=False, includeInbox=False):
        calls.append(includeMessages)
        return snapshot

    monkeypatch.setattr(discovery, "discoveryRun", scan)
    state = tmp_path / "state"
    args = [
        "mailAgent",
        "--plan",
        "--json",
        "--config",
        str(configPath),
        "--state",
        str(state),
    ]
    if confirm:
        args.append("--confirm")
    monkeypatch.setattr("sys.argv", args)
    cli.main()
    import json

    outputPath = state / "plan.json"
    assert outputPath.is_file()
    output = json.loads(outputPath.read_text())
    assert output["migrationPlan"]["executionEnabled"] is False
    assert "userSummary" not in output["migrationPlan"]
    assert calls == [True]
    if confirm:
        assert (
            json.loads((state / "latest.json").read_text())["migrationPlan"][
                "executionEnabled"
            ]
            is False
        )


def testCliExplicitJsonFile(config, tmp_path, monkeypatch):
    from mailAgent import cli
    import mailAgent.discovery as discovery

    configPath = tmp_path / "config.toml"
    configPath.write_text(
        (Path(__file__).parents[1] / "config.example.toml").read_text()
    )
    monkeypatch.setattr(cli.tomllib, "loads", lambda text: config)
    monkeypatch.setattr(
        discovery,
        "discoveryRun",
        lambda accounts, root, includeMessages=False, includeInbox=False: snapshotBuild(config),
    )
    outputPath = tmp_path / "exports" / "plan.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "mailAgent",
            "--plan",
            "--json",
            str(outputPath),
            "--config",
            str(configPath),
            "--state",
            str(tmp_path / "state"),
        ],
    )
    cli.main()
    assert outputPath.is_file()


def testReadablePlanSummary(config):
    plan = migrationPlan(config, snapshotBuild(config))
    lines = planSummaryLines(plan)
    text = "\n".join(lines)
    assert "Planning only - no mail has been changed." in text
    assert "Messages scanned:" in text
    assert "Proposed actions:" in text
    assert "By mailbox" in text
    assert "andy" in text


@pytest.mark.parametrize("kind", ["Trash", "Junk", "Drafts"])
def testSystemInventorySkipsHeaders(kind):
    client = Mock()
    inventory = messagesDiscover(
        client, [dict(path="INBOX." + kind, delimiter=".", attributes=[], messages=100)]
    )
    assert inventory["complete"] and not inventory["messages"]
    assert not client.mock_calls


def testAggregatedLegacyTrashAndSummary(config):
    snapshot = snapshotBuild(config)
    mailbox = snapshot["mailboxes"][2]
    mailbox["folders"].append(
        dict(path="INBOX.Trash", delimiter=".", attributes=[], messages=500)
    )
    mailbox["inventory"]["messages"].extend(
        dict(folder="INBOX.Trash", uid=str(i), uidValidity="42", year=None)
        for i in range(20)
    )
    plan = migrationPlan(config, snapshot)
    reviews = [r for r in plan["reviewQueue"] if r.get("folder") == "INBOX.Trash"]
    assert len(reviews) == 1
    assert reviews[0]["messageCount"] == 500
    assert reviews[0]["requiresRetentionDecision"]
    assert not any(p["source"]["folder"] == "INBOX.Trash" for p in plan["proposals"])
    assert plan["summary"] == dict(
        messagesScanned=26,
        proposals=6,
        reviewItems=1,
        systemFolderMessagesExcluded=500,
        messagesWithInvalidDates=20,
        systemFoldersWithUnknownCounts=0,
    )
    assert plan["executionEnabled"] is False


def testSentRequiresExplicitMapping(config):
    snapshot = snapshotBuild(config)
    mailbox = snapshot["mailboxes"][2]
    mailbox["folders"][1].update(
        path="INBOX.Sent", delimiter=".", attributes=["\\Sent"], messages=2
    )
    for message in mailbox["inventory"]["messages"]:
        message["folder"] = "INBOX.Sent"
    plan = migrationPlan(config, snapshot)
    assert len([r for r in plan["reviewQueue"] if r.get("systemFolder") == "sent"]) == 1
    assert not any(p["source"]["mailbox"] == "old" for p in plan["proposals"])
    config["mailboxes"][2]["folderMappings"] = {"INBOX.Sent": "Orders/Shop"}
    plan = migrationPlan(config, snapshot)
    assert len([p for p in plan["proposals"] if p["source"]["mailbox"] == "old"]) == 2



def testArchiveSenderClassificationAndPaypalContains(config):
    root = Path(config["mailboxes"][0]["localArchive"])
    finance = root / "Finance.sbd"
    finance.mkdir()
    paypal = finance / "PayPal"
    paypal.write_bytes(
        b"From sender@example Tue Jan 1 00:00:00 2025\n"
        b"From: service@paypal.com\n"
        b"Subject: receipt\n\n"
        b"body\n"
        b"From sender@example Tue Jan 2 00:00:00 2025\n"
        b"From: service@paypal.com\n"
        b"Subject: payment\n\n"
        b"body\n"
    )
    archive = archiveDiscover(root)
    mappings = folderMappingsBuild(
        config["mailboxes"][0],
        dict(folders=[dict(path="INBOX", delimiter=".", attributes=[])]),
        archive,
    )
    index = archiveSenderIndex(archive)
    exact = senderClassify("service@paypal.com", mappings, index)
    assert exact["mapping"]["canonical"] == "Finance/PayPal"
    assert exact["method"] == "archiveSenderExact"

    contains = senderClassify("notice@paypal-status.example", mappings, {})
    assert contains["mapping"]["canonical"] == "Finance/PayPal"
    assert contains["method"] == "senderContainsFolderName"


def testInboxInventoryCapturesSenderAndSubject():
    client = inventoryClient()
    inventory = inboxMessagesDiscover(
        client, [dict(path="INBOX", delimiter=".", attributes=[])]
    )
    assert inventory["complete"]
    assert len(inventory["messages"]) == 2


def testInterestingSenderPreferences(tmp_path):
    path = tmp_path / "interesting.json"
    assert not interestIs(interestLoad(path), "andy", "news@example.com")
    data = interestSet("andy", "News@Example.com", True, path)
    assert interestIs(data, "andy", "news@example.com")
    assert path.stat().st_mode & 0o077 == 0
    data = interestSet("andy", "news@example.com", False, path)
    assert not interestIs(data, "andy", "news@example.com")


def testPlanTabVisibleBeforePlanning(config):
    from mailAgent.auditUi import auditAppBuild
    from textual.widgets import Button, Static, TabPane

    snapshot = snapshotBuild(config)
    snapshot.pop("migrationPlan", None)

    async def uiInspect():
        app = auditAppBuild(snapshot)
        async with app.run_test(size=(120, 40)):
            assert app.query_one("#plan", TabPane)
            assert app.query_one("#run-planning", Button).label == "Run planning session"
            assert "No planning session" in str(
                app.query_one("#plan-summary", Static).render()
            )

    asyncio.run(uiInspect())


def testPlanButtonReturnsPlanningRequest(config):
    from mailAgent.auditUi import auditAppBuild
    from textual.widgets import Button, TabbedContent

    snapshot = snapshotBuild(config)

    async def uiInspect():
        app = auditAppBuild(snapshot)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one(TabbedContent).active = "plan"
            await pilot.pause()
            button = app.query_one("#run-planning", Button)
            button.focus()
            await pilot.press("enter")
            await pilot.pause()
        return app.return_value

    assert asyncio.run(uiInspect()) == "runPlanning"


def testPlanningRowsAreUserFacing():
    from mailAgent.auditUi import _planningRow

    mapping = dict(
        mailbox="andy",
        canonical="Finance/PayPal",
        local="/private/local/store",
        imap="Finance.PayPal",
        imapExists=False,
    )
    assert _planningRow("mappings", mapping) == (
        "andy",
        "Finance/PayPal",
        "Finance/PayPal",
        "Folder proposed",
    )

    proposal = dict(
        action="migrate",
        source=dict(
            mailbox="andy",
            folder="INBOX",
            uid="123",
            uidValidity="42",
            sender="service@paypal.com",
        ),
        year=2026,
        destination=dict(
            kind="imap",
            mailbox="andy",
            folder="Finance.PayPal",
            exists=False,
        ),
        requiresFolderCreation=True,
        classification=dict(reason="Archived PayPal sender history"),
    )
    row = _planningRow("proposals", proposal)
    assert row[:5] == (
        "andy",
        "service@paypal.com",
        2026,
        "Move",
        "andy: Finance/PayPal",
    )
    assert "UID" not in " ".join(str(value) for value in row)
    assert "create destination folder" in row[5]


def testHideMyEmailRelayDecode():
    assert senderRelayDecode(
        "bmwuk_at_service_bmw_com_x9b7cd6akmvy48_carg7807@icloud.com"
    ) == "bmwuk@service.bmw.com"
    assert senderRelayDecode(
        "community_at_warp_dev_x9b7aab5kmvyab_58rq7807@icloud.com"
    ) == "community@warp.dev"
    assert senderRelayDecode("normal@example.com") == "normal@example.com"
    assert senderRelayDecode("odd_at_value@icloud.com") == "odd_at_value@icloud.com"
