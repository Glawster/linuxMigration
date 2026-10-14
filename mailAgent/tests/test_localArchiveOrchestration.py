"""End-to-end tests for one verified IMAP-to-local archive action."""

from copy import deepcopy
import mailbox

import pytest

from mailAgent.executionPlan import executionActionId, executionPlanPrepare
from mailAgent.executionJournal import executionJournalLoad
from mailAgent.localArchiveOrchestration import localArchiveFileExecute

_BODY = (
    b"Date: Mon, 1 Jan 2024 10:00:00 +0000\r\n"
    b"From: sender@example.com\r\n"
    b"To: user@example.com\r\n"
    b"Subject: Local archive test\r\n"
    b"Message-ID: <local-archive@example.com>\r\n"
    b"\r\n"
    b"private body\r\n"
)


class Crash(BaseException):
    pass


class FakeImap:
    capabilities = (b"UIDPLUS",)

    def __init__(self):
        self.folders = {"INBOX": {"10": [_BODY, [r"\Seen"]]}}
        self.validity = {"INBOX": b"42"}
        self.selected = None
        self.readonly = True
        self.calls = []
        self.fail = None

    def select(self, folder, readonly=True):
        self.selected = folder[1:-1]
        self.readonly = readonly
        return ("OK", []) if self.selected in self.folders else ("NO", [])

    def response(self, name):
        if name == "UIDVALIDITY":
            return name, [self.validity[self.selected]]
        return name, [b"11"]

    def uid(self, command, *args):
        self.calls.append((command, self.selected, args))
        messages = self.folders[self.selected]
        if command == "FETCH":
            uid = args[0]
            if uid not in messages:
                return "OK", [None]
            body, flags = messages[uid]
            return "OK", [
                (
                    f'1 (UID {uid} FLAGS ({" ".join(flags)}) BODY[] {{{len(body)}}}'.encode(),
                    body,
                ),
                b")",
            ]
        if command == "STORE":
            assert not self.readonly
            if r"\Deleted" not in messages[args[0]][1]:
                messages[args[0]][1].append(r"\Deleted")
            if self.fail == "STORE":
                self.fail = None
                raise Crash()
            return "OK", []
        if command == "EXPUNGE":
            assert not self.readonly
            if r"\Deleted" in messages[args[0]][1]:
                del messages[args[0]]
            if self.fail == "EXPUNGE":
                self.fail = None
                raise Crash()
            return "OK", []
        raise AssertionError(command)


@pytest.fixture
def scenario(tmp_path):
    archiveRoot = tmp_path / "myMail"
    archiveRoot.mkdir()
    destination = archiveRoot / "PayPal"
    box = mailbox.mbox(destination, create=True)
    box.close()

    config = dict(
        general=dict(liveYear=2026),
        mailboxes=[
            dict(
                id="andy",
                host="imap.example.com",
                username="andy",
                port=993,
                role="personal",
                localArchive=str(archiveRoot),
                archiveFormat="thunderbird",
            )
        ],
    )
    entry = dict(
        source=dict(
            mailbox="andy", folder="INBOX", uidValidity="42", uid="10", seen=True
        ),
        disposition="file",
        readState="read",
        year=2024,
        decisionSource="sender",
        canonical="Finance/PayPal",
        destination=dict(
            kind="local",
            mailbox="andy",
            folder="Finance/PayPal",
            path=str(destination),
            format="thunderbird",
        ),
        requiresFolderCreation=False,
    )
    current = executionPlanPrepare(
        dict(schemaVersion=1, proposals=[entry], dispositions=[]), config
    )
    approved = deepcopy(current)
    approved["executionEnabled"] = True
    action = approved["entries"][0]
    action.update(approved=True, executionPermitted=True, folderCreationApproved=False)
    action["actionId"] = executionActionId(
        dict(action, configFingerprint=approved["configFingerprint"])
    )
    client = FakeImap()
    journal = tmp_path / "state/execution.sqlite3"

    def observe():
        fresh = deepcopy(current)
        if "10" not in client.folders["INBOX"]:
            fresh["entries"] = []
        return fresh

    def run():
        return localArchiveFileExecute(
            client,
            approved,
            config,
            observe,
            action["actionId"],
            confirm=True,
            path=journal,
        )

    return client, destination, journal, run


def testLocalCopyVerifyRemoveAndCompletedRetry(scenario):
    client, destination, journal, run = scenario

    assert run()["state"] == "completed"
    assert "10" not in client.folders["INBOX"]
    box = mailbox.mbox(destination, create=False)
    try:
        assert len(box) == 1
    finally:
        box.close()

    calls = list(client.calls)
    assert run()["state"] == "completed"
    assert calls == client.calls
    assert b"private body" not in journal.read_bytes()
    record = executionJournalLoad(journal)[0]
    assert record["verification"] == "local-archive-and-removal-verified"


def testCrashAfterStoreResumesWithoutDuplicate(scenario):
    client, destination, _, run = scenario
    client.fail = "STORE"

    with pytest.raises(Crash):
        run()
    assert "10" in client.folders["INBOX"]

    assert run()["state"] == "completed"
    assert "10" not in client.folders["INBOX"]
    box = mailbox.mbox(destination, create=False)
    try:
        assert len(box) == 1
    finally:
        box.close()


def testCrashAfterExpungeCompletesFromCheckpointedLocalProof(scenario):
    client, destination, _, run = scenario
    client.fail = "EXPUNGE"

    with pytest.raises(Crash):
        run()
    assert "10" not in client.folders["INBOX"]

    assert run()["state"] == "completed"
    box = mailbox.mbox(destination, create=False)
    try:
        assert len(box) == 1
    finally:
        box.close()
