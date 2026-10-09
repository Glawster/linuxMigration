"""Durable action state preserves verification and restart boundaries."""

from copy import deepcopy
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from mailAgent.executionPlan import executionActionId
from mailAgent.executionJournal import (
    executionJournalCompleted,
    executionJournalFinish,
    executionJournalHistory,
    executionJournalLoad,
    executionJournalPath,
    executionJournalRegister,
    executionJournalRetry,
    executionJournalStart,
)


@pytest.fixture
def action():
    result = dict(
        source=dict(
            mailbox="andy", folder="INBOX", uidValidity="42", uid="10", seen=True
        ),
        disposition="file",
        readState="read",
        year=2026,
        decisionSource="domain",
        canonical="Shopping/Amazon",
        destination=dict(kind="imap", mailbox="andy", folder="Shopping.Amazon"),
        requiresFolderCreation=False,
        folderCreationApproved=False,
        configFingerprint="a" * 64,
        approved=True,
        executionPermitted=True,
    )
    result["actionId"] = executionActionId(result)
    return result


@pytest.fixture
def path(tmp_path):
    return tmp_path / "state/execution.sqlite3"


def testMissingLoadDoesNotCreateState(path, monkeypatch, tmp_path):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    assert (
        executionJournalPath() == tmp_path / ".local/state/mailAgent/execution.sqlite3"
    )
    assert executionJournalLoad(path) == []
    assert executionJournalCompleted(path) == set()
    with pytest.raises(ValueError):
        executionJournalHistory("unknown", path)
    assert not path.parent.exists()


def testVerifiedCompletionAndRegistrationAreIdempotent(path, action):
    executionJournalRegister([action], path)
    executionJournalStart(action["actionId"], revalidated=True, path=path)
    executionJournalFinish(
        action["actionId"], "completed", verification="destination-verified", path=path
    )
    executionJournalRegister([action], path)
    executionJournalFinish(
        action["actionId"], "completed", verification="destination-verified", path=path
    )
    record = executionJournalLoad(path)[0]
    assert record["state"] == "completed" and record["attempts"] == 1
    assert record["startedAt"] and record["finishedAt"]
    assert not record["requiresVerification"]
    assert executionJournalCompleted(path) == {action["actionId"]}
    assert [
        entry["state"] for entry in executionJournalHistory(action["actionId"], path)
    ] == ["pending", "started", "completed"]
    assert path.stat().st_mode & 0o077 == 0
    assert path.parent.stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError):
        executionJournalStart(action["actionId"], revalidated=True, path=path)
    with pytest.raises(ValueError):
        executionJournalRetry(
            action["actionId"], revalidated=True, partialOutcomeVerified=True, path=path
        )
    with pytest.raises(ValueError):
        executionJournalFinish(
            action["actionId"], "failed", error="network-failure", path=path
        )


def testInterruptedActionRequiresReconciliationBeforeRetry(path, action):
    executionJournalRegister([action], path)
    executionJournalStart(action["actionId"], revalidated=True, path=path)
    assert executionJournalLoad(path)[0]["requiresVerification"]
    with pytest.raises(ValueError):
        executionJournalStart(action["actionId"], revalidated=True, path=path)
    for valid, verified in [(False, True), (True, False), (1, True)]:
        with pytest.raises(ValueError):
            executionJournalRetry(
                action["actionId"],
                revalidated=valid,
                partialOutcomeVerified=verified,
                path=path,
            )
    executionJournalRetry(
        action["actionId"], revalidated=True, partialOutcomeVerified=True, path=path
    )
    executionJournalStart(action["actionId"], revalidated=True, path=path)
    assert executionJournalLoad(path)[0]["attempts"] == 2


@pytest.mark.parametrize("state", ["blocked", "failed"])
def testFailuresRemainDurableAndCanBeReconciled(path, action, state):
    executionJournalRegister([action], path)
    if state == "failed":
        executionJournalStart(action["actionId"], revalidated=True, path=path)
    executionJournalFinish(action["actionId"], state, error="stale-source", path=path)
    record = executionJournalLoad(path)[0]
    assert record["state"] == state and record["error"] == "stale-source"
    executionJournalRetry(
        action["actionId"], revalidated=True, partialOutcomeVerified=True, path=path
    )
    assert executionJournalLoad(path)[0]["state"] == "pending"


@pytest.mark.parametrize(
    "verification", [None, "junk-state-verified", "local-copy-verified", "message body"]
)
def testUnverifiedOrWrongCompletionCannotBeRecorded(path, action, verification):
    executionJournalRegister([action], path)
    executionJournalStart(action["actionId"], revalidated=True, path=path)
    with pytest.raises(ValueError):
        executionJournalFinish(
            action["actionId"], "completed", verification=verification, path=path
        )
    assert executionJournalCompleted(path) == set()


@pytest.mark.parametrize(
    "disposition,verification",
    [
        ("ignore", "ignore-honoured"),
        ("junk", "junk-state-verified"),
        ("local", "local-archive-and-removal-verified"),
    ],
)
def testDispositionSpecificVerification(path, action, disposition, verification):
    if disposition == "local":
        action["destination"] = dict(
            kind="local",
            mailbox="andy",
            folder="Shopping/Amazon",
            path="/archive/Amazon",
            format="thunderbird",
        )
        action["year"] = 2025
    else:
        action["disposition"] = disposition
        action.pop("canonical")
        action.pop("destination")
        action.pop("requiresFolderCreation")
    action["actionId"] = executionActionId(action)
    executionJournalRegister([action], path)
    executionJournalStart(action["actionId"], revalidated=True, path=path)
    executionJournalFinish(
        action["actionId"], "completed", verification=verification, path=path
    )
    assert executionJournalCompleted(path) == {action["actionId"]}


def testConflictRollsBackEntireBatch(path, action):
    other = deepcopy(action)
    other["destination"]["folder"] = "Other"
    other["actionId"] = executionActionId(other)
    with pytest.raises(ValueError, match="Conflicting"):
        executionJournalRegister([action, other], path)
    assert executionJournalLoad(path) == []
    executionJournalRegister([action], path)
    assert len(executionJournalLoad(path)) == 1


def testJournalDoesNotPersistUntrustedExtrasOrExceptionText(path, action):
    action.update(password="SECRET", body="MESSAGE BODY")
    action["source"]["subject"] = "PRIVATE SUBJECT"
    executionJournalRegister([action], path)
    with pytest.raises(ValueError):
        executionJournalFinish(
            action["actionId"], "blocked", error="password SECRET", path=path
        )
    payload = path.read_bytes()
    assert all(
        value not in payload
        for value in (b"SECRET", b"MESSAGE BODY", b"PRIVATE SUBJECT")
    )


def testAtomicClaimPreventsTwoConcurrentStarts(path, action):
    executionJournalRegister([action], path)

    def start():
        try:
            executionJournalStart(action["actionId"], revalidated=True, path=path)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: start(), range(2))) == [False, True]
    assert executionJournalLoad(path)[0]["attempts"] == 1


def testCorruptOrUnsupportedJournalFailsClosed(path, action):
    executionJournalRegister([action], path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE actions SET state='completed', verification=NULL")
    with pytest.raises(ValueError, match="Unverified"):
        executionJournalLoad(path)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError, match="Unsupported"):
        executionJournalLoad(path)


def testSymlinkOrPublicJournalRejected(path, action, tmp_path):
    target = tmp_path / "target"
    target.write_text("do not overwrite")
    path.parent.mkdir()
    path.symlink_to(target)
    with pytest.raises(ValueError):
        executionJournalRegister([action], path)
    assert target.read_text() == "do not overwrite"
    path.unlink()
    path.write_text("public")
    path.chmod(0o644)
    with pytest.raises(ValueError):
        executionJournalLoad(path)


def testInvalidTransitionsDoNotAlterPendingState(path, action):
    executionJournalRegister([action], path)
    with pytest.raises(ValueError):
        executionJournalStart(action["actionId"], revalidated=False, path=path)
    with pytest.raises(ValueError):
        executionJournalFinish(
            action["actionId"],
            "completed",
            verification="destination-verified",
            path=path,
        )
    with pytest.raises(ValueError):
        executionJournalFinish(action["actionId"], "unknown", path=path)
    with pytest.raises(ValueError):
        executionJournalStart("unknown", revalidated=True, path=path)
    assert executionJournalLoad(path)[0]["attempts"] == 0


def testJournalRejectsChangedPayloadAndCorruptSourceKey(path, action):
    executionJournalRegister([action], path)
    changed = dict(action, requiresFolderCreation=True)
    with pytest.raises(ValueError, match="identity changed"):
        executionJournalRegister([changed], path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE actions SET source_key='wrong'")
    with pytest.raises(ValueError, match="Corrupt"):
        executionJournalLoad(path)


def testBrokenSymlinkLoadIsRejected(path, tmp_path):
    path.parent.mkdir()
    path.symlink_to(tmp_path / "missing")
    with pytest.raises(ValueError):
        executionJournalLoad(path)
