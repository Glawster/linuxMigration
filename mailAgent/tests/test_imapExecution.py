"""Single-message filing, verified removal and interruption reconciliation."""

from copy import deepcopy

import pytest

from mailAgent.executionPlan import executionActionId, executionPlanPrepare
from mailAgent.executionJournal import executionJournalLoad, executionJournalCopyProof
from mailAgent.imapExecution import imapFileExecute, ImapExecutionBlocked

_BODY = b"Date: Thu, 1 Oct 2026 12:00:00 +0100\r\nFrom: example@example.com\r\n\r\nprivate body\r\n"


class Crash(BaseException):
    pass


class FakeImap:
    capabilities = (b"UIDPLUS",)

    def __init__(self):
        self.folders = {
            "INBOX": {"10": [_BODY, [r"\Seen"]], "11": [b"other", [r"\Deleted"]]}
        }
        self.validity = {"INBOX": b"42", "Shopping.Amazon": b"77"}
        self.selected = None
        self.calls = []
        self.fail = None
        self.corrupt = False
        self.duplicate = False
        self.rejectCopy = False

    def interrupt(self, step):
        if self.fail == step:
            self.fail = None
            raise Crash()

    def list(self):
        return "OK", [f'(\\HasNoChildren) "." "{f}"'.encode() for f in self.folders]

    def create(self, folder):
        name = folder[1:-1]
        self.calls.append(("CREATE", name))
        self.folders.setdefault(name, {})
        self.interrupt("CREATE")
        return "OK", []

    def select(self, folder, readonly=True):
        self.selected = folder[1:-1]
        self.readonly = readonly
        if self.selected not in self.folders:
            return "NO", []
        return "OK", []

    def response(self, name):
        if name == "UIDVALIDITY":
            return name, [self.validity[self.selected]]
        return name, [
            str(max([int(u) for u in self.folders[self.selected]] + [0]) + 1).encode()
        ]

    def uid(self, command, *args):
        messages = self.folders[self.selected]
        self.calls.append((command, self.selected, args))
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
        if command == "SEARCH":
            start = int(args[-1].split(":")[0])
            return "OK", [b" ".join(u.encode() for u in messages if int(u) >= start)]
        if command == "COPY":
            self.interrupt("before-COPY")
            if self.rejectCopy:
                return "NO", []
            destination = self.folders[args[1][1:-1]]
            uid = str(max([int(u) for u in destination] + [0]) + 1)
            destination[uid] = deepcopy(messages[args[0]])
            if self.corrupt:
                destination[uid][0] = b"corrupt"
            if self.duplicate:
                destination[str(int(uid) + 1)] = deepcopy(destination[uid])
            self.interrupt("COPY")
        elif command == "STORE":
            assert not self.readonly
            messages[args[0]][1].append(r"\Deleted")
            self.interrupt("STORE")
        elif command == "EXPUNGE":
            assert not self.readonly
            if r"\Deleted" in messages[args[0]][1]:
                del messages[args[0]]
            self.interrupt("EXPUNGE")
        else:
            raise AssertionError(command)
        return "OK", []


@pytest.fixture
def scenario(tmp_path):
    config = dict(
        general=dict(liveYear=2026),
        mailboxes=[
            dict(
                id="andy",
                host="imap.example.com",
                username="andy",
                port=993,
                role="personal",
            )
        ],
    )
    entry = dict(
        source=dict(
            mailbox="andy", folder="INBOX", uidValidity="42", uid="10", seen=True
        ),
        disposition="file",
        readState="read",
        year=2026,
        decisionSource="domain",
        canonical="Shopping/Amazon",
        destination=dict(kind="imap", mailbox="andy", folder="Shopping.Amazon"),
        requiresFolderCreation=True,
    )
    current = executionPlanPrepare(
        dict(schemaVersion=1, proposals=[entry], dispositions=[]), config
    )
    approved = deepcopy(current)
    approved["executionEnabled"] = True
    action = approved["entries"][0]
    action.update(approved=True, executionPermitted=True, folderCreationApproved=True)
    action["actionId"] = executionActionId(
        dict(action, configFingerprint=approved["configFingerprint"])
    )
    client = FakeImap()
    path = tmp_path / "state/execution.sqlite3"

    def observe():
        fresh = deepcopy(current)
        if "10" not in client.folders["INBOX"]:
            fresh["entries"] = []
        return fresh

    def run(**kwargs):
        return imapFileExecute(
            client,
            approved,
            config,
            observe,
            action["actionId"],
            path=path,
            **dict(dict(confirm=True), **kwargs),
        )

    return client, path, run, approved, config, current


def testCopyVerifyRemoveAndCompletedRetry(scenario):
    client, path, run, *_ = scenario
    assert run()["state"] == "completed"
    assert client.folders["Shopping.Amazon"]["1"][0] == _BODY
    assert "10" not in client.folders["INBOX"]
    assert "11" in client.folders["INBOX"]
    calls = list(client.calls)
    assert run()["state"] == "completed"
    assert calls == client.calls
    assert b"private body" not in path.read_bytes()
    commands = [c[0] for c in calls]
    assert (
        commands.index("COPY")
        < commands.index("SEARCH")
        < commands.index("STORE")
        < commands.index("EXPUNGE")
    )


@pytest.mark.parametrize("step", ["CREATE", "COPY", "STORE", "EXPUNGE"])
def testCrashResumesWithoutDuplicate(scenario, step):
    client, path, run, *_ = scenario
    client.fail = step
    with pytest.raises(Crash):
        run()
    assert executionJournalLoad(path)[0]["requiresVerification"]
    assert run()["state"] == "completed"
    assert len(client.folders["Shopping.Amazon"]) == 1
    assert sum(c[0] == "COPY" for c in client.calls) == 1
    assert sum(c[0] == "CREATE" for c in client.calls) == 1


@pytest.mark.parametrize("mode", ["corrupt", "duplicate", "rejectCopy", "before-COPY"])
def testUncertainOrUnverifiedCopyPreservesSourceAndNeverRecopies(scenario, mode):
    client, path, run, *_ = scenario
    if mode == "before-COPY":
        client.fail = mode
    else:
        setattr(client, mode, True)
    with pytest.raises((ImapExecutionBlocked, Crash)):
        run()
    with pytest.raises(ImapExecutionBlocked):
        run()
    assert client.folders["INBOX"]["10"][1] == [r"\Seen"]
    assert sum(c[0] == "COPY" for c in client.calls) == 1
    assert not any(c[0] in ("STORE", "EXPUNGE") for c in client.calls)


@pytest.mark.parametrize(
    "mode",
    [
        "confirm",
        "uidValidity",
        "unread",
        "old",
        "deleted",
        "missing",
        "capability",
        "unapproved",
        "role",
        "destination",
        "creation",
    ],
)
def testPreconditionsDoNotMutate(scenario, mode):
    client, path, run, approved, config, current = scenario
    if mode == "uidValidity":
        client.validity["INBOX"] = b"99"
    elif mode == "unread":
        client.folders["INBOX"]["10"][1] = []
    elif mode == "old":
        client.folders["INBOX"]["10"][0] = _BODY.replace(b"2026", b"2025")
    elif mode == "deleted":
        client.folders["INBOX"]["10"][1].append(r"\Deleted")
    elif mode == "missing":
        del client.folders["INBOX"]["10"]
    elif mode == "capability":
        client.capabilities = ()
    elif mode == "unapproved":
        approved["executionEnabled"] = False
    elif mode == "role":
        config["mailboxes"][0]["role"] = "support"
    elif mode == "destination":
        current["entries"][0]["destination"]["folder"] = "Other"
    elif mode == "creation":
        action = approved["entries"][0]
        action["folderCreationApproved"] = False
        action["actionId"] = executionActionId(
            dict(action, configFingerprint=approved["configFingerprint"])
        )
    with pytest.raises(ValueError):
        run(confirm=mode != "confirm")
    assert not any(c[0] in ("CREATE", "COPY", "STORE", "EXPUNGE") for c in client.calls)


def testExistingDestinationIsIdempotentAndOldIdenticalMessageIsNotProof(scenario):
    client, path, run, *_ = scenario
    client.folders["Shopping.Amazon"] = {"5": [_BODY, [r"\Seen"]]}
    assert run()["state"] == "completed"
    assert len(client.folders["Shopping.Amazon"]) == 2
    assert not any(c[0] == "CREATE" for c in client.calls)


def testDestinationUidValidityChangeBlocksResume(scenario):
    client, path, run, *_ = scenario
    client.fail = "COPY"
    with pytest.raises(Crash):
        run()
    client.validity["Shopping.Amazon"] = b"88"
    with pytest.raises(ImapExecutionBlocked, match="destination-changed"):
        run()
    assert "10" in client.folders["INBOX"]
    assert not any(c[0] == "STORE" for c in client.calls)


def testCopyProofIsImmutableAndRejectsPrivateData(scenario):
    client, path, run, approved, *_ = scenario
    client.fail = "COPY"
    with pytest.raises(Crash):
        run()
    actionId = approved["entries"][0]["actionId"]
    proof = executionJournalCopyProof(actionId, path=path)
    for changed in (
        dict(proof, digest="b" * 64),
        dict(proof, body="private"),
        dict(proof, uidNext="0"),
    ):
        with pytest.raises(ValueError):
            executionJournalCopyProof(actionId, changed, path)
    assert executionJournalCopyProof(actionId, path=path) == proof


def testConcurrentExecutorCannotEnterMutation(scenario):
    import fcntl
    import os

    client, path, run, *_ = scenario
    path.parent.mkdir(parents=True)
    descriptor = os.open(str(path) + ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            run()
        assert not client.calls
    finally:
        os.close(descriptor)


def testNetworkProbeFailureIsJournalledWithoutServerText(scenario):
    client, path, run, *_ = scenario

    def broken(*args, **kwargs):
        raise OSError("private server text")

    client.select = broken
    with pytest.raises(OSError):
        run()
    record = executionJournalLoad(path)[0]
    assert record["state"] == "blocked"
    assert record["error"] == "network-failure"
    assert b"private server text" not in path.read_bytes()


def testNetworkCopyFailureCanReconcile(scenario):
    client, path, run, *_ = scenario
    original = client.uid

    def broken(command, *args):
        result = original(command, *args)
        if command == "COPY":
            raise OSError("lost response")
        return result

    client.uid = broken
    with pytest.raises(OSError):
        run()
    assert executionJournalLoad(path)[0]["state"] == "failed"
    client.uid = original
    assert run()["state"] == "completed"
    assert sum(c[0] == "COPY" for c in client.calls) == 1
