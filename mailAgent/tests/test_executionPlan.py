"""Execution approval is independent of filing decisions and fresh eligibility."""

from copy import deepcopy

import pytest

from mailAgent.executionPlan import (
    executionActionId,
    executionActionValidate,
    executionConfigFingerprint,
    executionPlanBuild,
    executionPlanPrepare,
)


@pytest.fixture
def config(tmp_path):
    return dict(
        general=dict(liveYear=2026),
        mailboxes=[
            dict(
                id="andy",
                host="imap.example.com",
                port=993,
                username="andy@example.com",
                role="personal",
                localArchive=str(tmp_path / "myMail"),
                archiveFormat="thunderbird",
                junkKeyword="$Junk",
                passwordEnv="MAIL_PASSWORD",
            )
        ],
    )


@pytest.fixture
def filing(config):
    return dict(
        schemaVersion=1,
        executionEnabled=False,
        proposals=[
            dict(
                source=dict(
                    mailbox="andy",
                    folder="INBOX",
                    uidValidity="42",
                    uid="10",
                    seen=True,
                    sender="sender@example.com",
                    domain="example.com",
                ),
                disposition="file",
                readState="read",
                year=2026,
                decisionSource="domain",
                canonical="Shopping/Amazon",
                destination=dict(
                    kind="imap", mailbox="andy", folder="Shopping.Amazon", exists=True
                ),
                requiresFolderCreation=False,
                executionPermitted=False,
                sourceRemovalAllowed=False,
            )
        ],
        dispositions=[],
    )


def approve(envelope, creation=False):
    result = deepcopy(envelope)
    result["executionEnabled"] = True
    for entry in result["entries"]:
        entry.update(
            approved=True, executionPermitted=True, folderCreationApproved=creation
        )
        entry["actionId"] = executionActionId(
            dict(entry, configFingerprint=result["configFingerprint"])
        )
    return result


def testPrepareNeverApprovesAndDoesNotChangePlan(config, filing):
    before = deepcopy(filing)
    current = executionPlanPrepare(filing, config)
    assert filing == before
    assert current["executionEnabled"] is False
    result = executionPlanBuild(current, config, current)
    assert not result["actions"] and result["blocked"]
    assert "sender" not in current["entries"][0]["source"]


def testApprovedFreshActionHasStableIdentityAndCompletedIsSkipped(config, filing):
    current = executionPlanPrepare(filing, config)
    approved = approve(current)
    result = executionPlanBuild(approved, config, current)
    assert not result["blocked"]
    assert result["executionEnabled"] is False
    action = result["actions"][0]
    assert executionActionValidate(action) == action
    assert action["actionId"] == approved["entries"][0]["actionId"]
    assert executionPlanBuild(approved, config, current, {action["actionId"]})[
        "completed"
    ] == [action["actionId"]]
    assert not executionPlanBuild(approved, config, current, {action["actionId"]})[
        "actions"
    ]
    changed = deepcopy(action)
    changed["destination"]["folder"] = "Other"
    assert executionActionId(changed) != action["actionId"]
    with pytest.raises(ValueError):
        executionActionValidate(changed)


@pytest.mark.parametrize(
    "change",
    [
        "uid",
        "uidValidity",
        "seen",
        "folder",
        "destination",
        "year",
        "disposition",
        "decisionSource",
        "missing",
    ],
)
def testFreshChangesBlockWithoutGuessing(config, filing, change):
    current = executionPlanPrepare(filing, config)
    approved = approve(current)
    fresh = deepcopy(current)
    entry = fresh["entries"][0]
    if change in ("uid", "uidValidity"):
        entry["source"][change] = "99"
    elif change == "seen":
        entry["source"]["seen"] = False
    elif change == "folder":
        entry["source"]["folder"] = "Archive"
    elif change == "destination":
        entry["destination"]["folder"] = "Other"
    elif change == "year":
        entry["year"] = 2025
    elif change == "disposition":
        entry["disposition"] = "ignore"
    elif change == "decisionSource":
        entry["decisionSource"] = "sender"
    else:
        fresh["entries"] = []
    result = executionPlanBuild(approved, config, fresh)
    assert not result["actions"] and len(result["blocked"]) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("host", "other.example.com"),
        ("username", "other"),
        ("port", 143),
        ("role", "shared"),
        ("localArchive", "/other"),
        ("folderMappings", {"A": "B"}),
    ],
)
def testConfigurationChangesInvalidateEnvelope(config, filing, field, value):
    current = executionPlanPrepare(filing, config)
    config["mailboxes"][0][field] = value
    with pytest.raises(ValueError, match="identity changed"):
        executionPlanBuild(approve(current), config, current)


def testCredentialsAreNeitherBoundNorPersisted(config):
    original = executionConfigFingerprint(config)
    config["mailboxes"][0].update(passwordEnv="NEW_PASSWORD", password="DO_NOT_STORE")
    assert executionConfigFingerprint(config) == original


@pytest.mark.parametrize("role", ["legacy", "shared", "support"])
def testOnlyPersonalExecution(config, filing, role):
    config["mailboxes"][0]["role"] = role
    current = executionPlanPrepare(filing, config)
    assert not executionPlanBuild(approve(current), config, current)["actions"]


def testFolderCreationRequiresSeparateApprovalAndExistingFolderIsIdempotent(
    config, filing
):
    filing["proposals"][0]["requiresFolderCreation"] = True
    current = executionPlanPrepare(filing, config)
    assert not executionPlanBuild(approve(current), config, current)["actions"]
    approved = approve(current, creation=True)
    action = executionPlanBuild(approved, config, current)["actions"][0]
    current["entries"][0]["requiresFolderCreation"] = False
    assert (
        executionPlanBuild(approved, config, current)["actions"][0]["actionId"]
        == action["actionId"]
    )


def testVanishedDestinationWithoutCreationApprovalBlocks(config, filing):
    current = executionPlanPrepare(filing, config)
    approved = approve(current)
    current["entries"][0]["requiresFolderCreation"] = True
    assert not executionPlanBuild(approved, config, current)["actions"]


@pytest.mark.parametrize("disposition", ["ignore", "junk"])
def testNonFileHasNoDestinationAndNeedsIndependentApproval(config, filing, disposition):
    entry = filing["proposals"].pop()
    entry.update(disposition=disposition)
    for key in ("canonical", "destination", "requiresFolderCreation"):
        entry.pop(key)
    filing["dispositions"] = [entry]
    current = executionPlanPrepare(filing, config)
    result = executionPlanBuild(approve(current), config, current)
    assert len(result["actions"]) == 1
    assert "destination" not in result["actions"][0]
    if disposition == "junk":
        config["mailboxes"][0].pop("junkKeyword")
        current = executionPlanPrepare(filing, config)
        assert not executionPlanBuild(approve(current), config, current)["actions"]


def testOldThunderbirdActionAndEscapingArchiveBlocked(config, filing, tmp_path):
    entry = filing["proposals"][0]
    entry["year"] = 2025
    entry["destination"] = dict(
        kind="local",
        mailbox="andy",
        folder="Shopping/Amazon",
        format="thunderbird",
        path=str(tmp_path / "myMail/Shopping.sbd/Amazon"),
    )
    current = executionPlanPrepare(filing, config)
    assert len(executionPlanBuild(approve(current), config, current)["actions"]) == 1
    entry["destination"]["path"] = str(tmp_path / "outside")
    current = executionPlanPrepare(filing, config)
    assert not executionPlanBuild(approve(current), config, current)["actions"]


def testConflictingSourcesBlockBothActions(config, filing):
    current = executionPlanPrepare(filing, config)
    current["entries"].append(deepcopy(current["entries"][0]))
    current["entries"][1]["destination"]["folder"] = "Other"
    result = executionPlanBuild(approve(current), config, current)
    assert not result["actions"] and len(result["blocked"]) == 2


@pytest.mark.parametrize("change", ["schema", "approval", "permission", "id"])
def testMalformedOrUnapprovedEnvelopeIsRejected(config, filing, change):
    current = executionPlanPrepare(filing, config)
    approved = approve(current)
    if change == "schema":
        approved["schemaVersion"] = True
        with pytest.raises(ValueError):
            executionPlanBuild(approved, config, current)
        return
    key = {
        "approval": "approved",
        "permission": "executionPermitted",
        "id": "actionId",
    }[change]
    approved["entries"][0][key] = False
    assert not executionPlanBuild(approved, config, current)["actions"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("uid", "0"),
        ("uid", "4294967296"),
        ("uidValidity", "unknown"),
        ("mailbox", ""),
        ("folder", "INBOX\n"),
    ],
)
def testMalformedSourceIdentityBlocks(config, filing, field, value):
    current = executionPlanPrepare(filing, config)
    approved = approve(current)
    approved["entries"][0]["source"][field] = value
    result = executionPlanBuild(approved, config, current)
    assert result["actions"] == [] and result["blocked"][0]["index"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("disposition", "delete"),
        ("decisionSource", "body text"),
        ("year", "message body"),
        ("year", True),
        ("folderCreationApproved", 1),
        ("requiresFolderCreation", "yes"),
        ("canonical", "Shopping/../Amazon"),
    ],
)
def testInvalidActionMetadataBlocks(config, filing, field, value):
    current = executionPlanPrepare(filing, config)
    approved = approve(current)
    approved["entries"][0][field] = value
    assert not executionPlanBuild(approved, config, current)["actions"]


@pytest.mark.parametrize(
    "field,value", [("kind", "ftp"), ("mailbox", "kathy"), ("folder", "INBOX")]
)
def testUnsafeImapTargetsBlock(config, filing, field, value):
    filing["proposals"][0]["destination"][field] = value
    if field == "kind":
        with pytest.raises(ValueError):
            executionPlanPrepare(filing, config)
        return
    current = executionPlanPrepare(filing, config)
    assert not executionPlanBuild(approve(current), config, current)["actions"]


@pytest.mark.parametrize("year", [None, 2025])
def testImapFilingRequiresLiveYear(config, filing, year):
    filing["proposals"][0]["year"] = year
    current = executionPlanPrepare(filing, config)
    assert not executionPlanBuild(approve(current), config, current)["actions"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("format", "maildir"),
        ("path", {}),
        ("path", None),
        ("path", "relative"),
        ("folder", "Other"),
    ],
)
def testLocalArchiveIdentityIsExplicitAndThunderbirdCompatible(
    config, filing, field, value
):
    entry = filing["proposals"][0]
    entry["year"] = 2025
    entry["destination"] = dict(
        kind="local",
        mailbox="andy",
        folder="Shopping/Amazon",
        format="thunderbird",
        path=config["mailboxes"][0]["localArchive"] + "/Shopping.sbd/Amazon",
    )
    entry["destination"][field] = value
    if field == "format" or value == {}:
        with pytest.raises(ValueError):
            executionPlanPrepare(filing, config)
        return
    current = executionPlanPrepare(filing, config)
    assert not executionPlanBuild(approve(current), config, current)["actions"]
    if field == "path":
        candidate = dict(
            approve(current)["entries"][0],
            configFingerprint=current["configFingerprint"],
        )
        with pytest.raises(ValueError):
            executionActionValidate(candidate)


def testEnvelopeAndConfigurationStructureRejectsMalformedData(config, filing):
    for invalid in (
        {},
        dict(mailboxes=[]),
        dict(mailboxes=[config["mailboxes"][0]] * 2),
    ):
        with pytest.raises(ValueError):
            executionConfigFingerprint(invalid)
    for schema in (2, True):
        with pytest.raises(ValueError):
            executionPlanPrepare(dict(filing, schemaVersion=schema), config)
    current = executionPlanPrepare(filing, config)
    for field, value in (
        ("entries", {}),
        ("executionEnabled", 1),
        ("configFingerprint", "z" * 64),
    ):
        invalid = dict(current, **{field: value})
        with pytest.raises(ValueError):
            executionPlanBuild(invalid, config, current)


def testJunkCannotSmuggleDestinationOrGuessKeyword(config, filing):
    entry = filing["proposals"][0]
    entry["disposition"] = "junk"
    with pytest.raises(ValueError):
        executionPlanPrepare(filing, config)
    entry.pop("destination")
    entry.pop("canonical")
    config["mailboxes"][0]["junkKeyword"] = "junk flag"
    current = executionPlanPrepare(filing, config)
    assert not executionPlanBuild(approve(current), config, current)["actions"]


def testApprovedStaleActionCanBeDurablyBlocked(config, filing, tmp_path):
    from mailAgent.executionJournal import (
        executionJournalRegister,
        executionJournalFinish,
        executionJournalLoad,
    )

    current = executionPlanPrepare(filing, config)
    approved = approve(current)
    current["entries"] = []
    blocked = executionPlanBuild(approved, config, current)["blocked"][0]
    action = blocked["action"]
    path = tmp_path / "execution.sqlite3"
    executionJournalRegister([action], path)
    executionJournalFinish(
        action["actionId"], "blocked", error="stale-source", path=path
    )
    assert executionJournalLoad(path)[0]["state"] == "blocked"
    assert executionJournalLoad(path)[0]["startedAt"] is None
