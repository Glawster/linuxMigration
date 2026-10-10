"""One explicitly invoked IMAP filing operation; no discovery or UI wiring."""

import fcntl
from hashlib import sha256
import os
from pathlib import Path
import stat
from typing import Any, Callable

from mailAgent.executionJournal import (
    executionJournalCopyProof,
    executionJournalFinish,
    executionJournalLoad,
    executionJournalPath,
    executionJournalRegister,
    executionJournalRetry,
    executionJournalStart,
)
from mailAgent.executionPlan import executionActionValidate, executionPlanBuild
from mailAgent.imapDiscovery import folderParse, _pathQuote
from mailAgent.messageInventory import messageParse


class ImapExecutionBlocked(ValueError):
    """A fixed safe reason for refusing a mailbox operation."""


## execution


def imapFileExecute(
    client: Any,
    approved: dict,
    config: dict,
    currentObserve: Callable[[], dict],
    actionId: str,
    *,
    confirm: bool = False,
    path: Path | None = None,
) -> dict:
    """File exactly one action on an exclusively owned authenticated connection.

    The caller binds this connection to the configured source account. The
    callback must rebuild a fresh read-only execution envelope, including rules.
    Explicit confirmation is independent of approval. No live CLI/TUI calls this.
    """
    if confirm is not True:
        raise ImapExecutionBlocked("unapproved")
    selected = path or executionJournalPath()
    selected.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(
        str(selected) + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
    )
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode) or mode & 0o077:
            raise ImapExecutionBlocked("environment-untrusted")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return _fileExecute(
            client, approved, config, currentObserve, actionId, selected
        )
    finally:
        os.close(descriptor)


def imapFolderEnsure(client: Any, action: dict) -> None:
    """Create only the exact approved path; existing selectable paths succeed."""
    action = executionActionValidate(action)
    if action["disposition"] != "file" or action["destination"]["kind"] != "imap":
        raise ImapExecutionBlocked("unsupported")
    folder = action["destination"]["folder"]
    if _folderExists(client, folder):
        return
    if not action["folderCreationApproved"]:
        raise ImapExecutionBlocked("unapproved")
    # A failed CREATE may race another creator. Re-observe the exact path.
    client.create(_pathQuote(folder))
    if not _folderExists(client, folder):
        raise ImapExecutionBlocked("destination-changed")


## workflow


def _fileExecute(
    client: Any,
    approved: dict,
    config: dict,
    observe: Callable[[], dict],
    actionId: str,
    path: Path,
) -> dict:
    action, result = _actionSelect(approved, config, observe, actionId)
    executionJournalRegister([action], path)
    record = _recordRead(actionId, path)
    if record["state"] == "completed":
        return record
    proof = executionJournalCopyProof(actionId, path=path)
    try:
        source = _attemptPrepare(client, action, result, record, proof, path)
        if proof is None:
            proof = _copyStart(client, action, source, path)
        _destinationVerify(client, action, proof)
        proof = _sourceRemove(client, action, proof, path)
        if _sourceRead(client, action) is not None:
            raise ImapExecutionBlocked("verification-failed")
        _destinationVerify(client, action, proof)
        executionJournalFinish(
            actionId, "completed", verification="destination-verified", path=path
        )
    except Exception as error:
        _failureRecord(actionId, error, path)
        raise
    return _recordRead(actionId, path)


def _actionSelect(
    approved: dict, config: dict, observe: Callable[[], dict], actionId: str
) -> tuple[dict, dict]:
    # Validate the envelope/config/scope even when resuming after source removal.
    result = executionPlanBuild(approved, config, observe())
    candidates = result["actions"] + [
        entry["action"] for entry in result["blocked"] if "action" in entry
    ]
    matches = [a for a in candidates if a["actionId"] == actionId]
    if len(matches) != 1:
        raise ImapExecutionBlocked("unapproved")
    action = matches[0]
    if (
        action["disposition"] != "file"
        or action["destination"]["kind"] != "imap"
        or action["year"] != config["general"]["liveYear"]
        or next(
            a for a in config["mailboxes"] if a["id"] == action["source"]["mailbox"]
        )["role"]
        != "personal"
        or action["destination"]["mailbox"] != action["source"]["mailbox"]
        or action["destination"]["folder"].upper() == "INBOX"
    ):
        raise ImapExecutionBlocked("unsupported")
    return action, result


def _attemptPrepare(
    client: Any,
    action: dict,
    result: dict,
    record: dict,
    proof: dict | None,
    path: Path,
) -> tuple[bytes, bytes] | None:
    actionId = action["actionId"]
    capabilities = {
        c.decode().upper() if isinstance(c, bytes) else c.upper()
        for c in client.capabilities
    }
    if "UIDPLUS" not in capabilities:
        raise ImapExecutionBlocked("unsupported")
    fresh = any(a["actionId"] == actionId for a in result["actions"])
    # Only our own removal intent permits a missing source on restart.
    if not fresh and not (proof and proof["removing"]):
        raise ImapExecutionBlocked("stale-source")
    source = _sourceRead(client, action)
    if source is None and not (proof and proof["removing"]):
        raise ImapExecutionBlocked("stale-source")
    if source is not None:
        if not fresh:
            raise ImapExecutionBlocked("stale-source")
        _sourceValidate(source, action, allowDeleted=bool(proof and proof["removing"]))
        if proof and sha256(source[1]).hexdigest() != proof["digest"]:
            raise ImapExecutionBlocked("stale-source")
    if proof is not None:
        _destinationVerify(client, action, proof)
    if record["state"] != "pending" or record["startedAt"]:
        executionJournalRetry(
            actionId, revalidated=True, partialOutcomeVerified=True, path=path
        )
    executionJournalStart(actionId, revalidated=True, path=path)
    return source


def _copyStart(
    client: Any, action: dict, source: tuple[bytes, bytes], path: Path
) -> dict:
    actionId = action["actionId"]
    imapFolderEnsure(client, action)
    _select(client, action["destination"]["folder"])
    proof = dict(
        digest=sha256(source[1]).hexdigest(),
        uidValidity=_responseNumber(client, "UIDVALIDITY"),
        uidNext=_responseNumber(client, "UIDNEXT"),
        removing=False,
    )
    # Recheck eligibility immediately before committing and sending COPY.
    source = _sourceRead(client, action)
    if source is None:
        raise ImapExecutionBlocked("stale-source")
    _sourceValidate(source, action)
    if sha256(source[1]).hexdigest() != proof["digest"]:
        raise ImapExecutionBlocked("stale-source")
    executionJournalCopyProof(actionId, proof, path)
    _ok(
        client.uid(
            "COPY",
            action["source"]["uid"],
            _pathQuote(action["destination"]["folder"]),
        )
    )
    return proof


def _failureRecord(actionId: str, error: Exception, path: Path) -> None:
    latest = next(
        r for r in executionJournalLoad(path) if r["action"]["actionId"] == actionId
    )
    if latest["state"] == "pending":
        executionJournalFinish(
            actionId,
            (
                "blocked"
                if isinstance(error, ImapExecutionBlocked)
                or latest["startedAt"] is None
                else "failed"
            ),
            error=(
                str(error)
                if isinstance(error, ImapExecutionBlocked)
                else "network-failure"
            ),
            path=path,
        )


def _recordRead(actionId: str, path: Path) -> dict:
    return next(
        r for r in executionJournalLoad(path) if r["action"]["actionId"] == actionId
    )


def _sourceRemove(client: Any, action: dict, proof: dict, path: Path) -> dict:
    actionId = action["actionId"]
    source = _sourceRead(client, action, writable=True)
    if source is not None:
        _sourceValidate(source, action, allowDeleted=proof["removing"])
        if sha256(source[1]).hexdigest() != proof["digest"]:
            raise ImapExecutionBlocked("stale-source")
        proof = dict(proof, removing=True)
        executionJournalCopyProof(actionId, proof, path)
        uid = action["source"]["uid"]
        _ok(client.uid("STORE", uid, "+FLAGS.SILENT", r"(\Deleted)"))
        _ok(client.uid("EXPUNGE", uid))
    elif not proof["removing"]:
        raise ImapExecutionBlocked("stale-source")
    return proof


## probes


def _destinationVerify(client: Any, action: dict, proof: dict) -> None:
    _select(client, action["destination"]["folder"])
    if _responseNumber(client, "UIDVALIDITY") != proof["uidValidity"]:
        raise ImapExecutionBlocked("destination-changed")
    rows = _ok(client.uid("SEARCH", None, "UID", proof["uidNext"] + ":*"))
    if len(rows) != 1 or not isinstance(rows[0], bytes):
        raise ImapExecutionBlocked("verification-failed")
    matches = []
    for raw in rows[0].split():
        if not raw.isdigit():
            raise ImapExecutionBlocked("verification-failed")
        # IMAP reversed ranges can include the previous last UID in an empty range.
        if int(raw) < int(proof["uidNext"]):
            continue
        message = _messageRead(client, raw.decode())
        if message and sha256(message[1]).hexdigest() == proof["digest"]:
            matches.append(raw)
    if len(matches) != 1:
        raise ImapExecutionBlocked("verification-failed")


def _folderExists(client: Any, folder: str) -> bool:
    rows = _ok(client.list())
    for row in rows or []:
        if row is None:
            continue
        parsed = folderParse(row)
        if parsed["path"] == folder:
            if "\\noselect" in {flag.lower() for flag in parsed["attributes"]}:
                raise ImapExecutionBlocked("destination-changed")
            return True
    return False


def _messageRead(client: Any, uid: str) -> tuple[bytes, bytes] | None:
    rows = _ok(client.uid("FETCH", uid, "(UID FLAGS BODY.PEEK[])"))
    messages = [r for r in rows or [] if isinstance(r, tuple)]
    if not messages:
        return None
    if (
        len(messages) != 1
        or len(messages[0]) != 2
        or not all(isinstance(v, bytes) for v in messages[0])
    ):
        raise ImapExecutionBlocked("verification-failed")
    parsed = messageParse(*messages[0], "INBOX", "1")
    if parsed["uid"] != uid:
        raise ImapExecutionBlocked("stale-source")
    return messages[0]


def _sourceRead(
    client: Any, action: dict, writable: bool = False
) -> tuple[bytes, bytes] | None:
    _select(client, action["source"]["folder"], writable)
    if _responseNumber(client, "UIDVALIDITY") != action["source"]["uidValidity"]:
        raise ImapExecutionBlocked("stale-source")
    return _messageRead(client, action["source"]["uid"])


def _sourceValidate(
    source: tuple[bytes, bytes], action: dict, allowDeleted: bool = False
) -> None:
    parsed = messageParse(
        *source, action["source"]["folder"], action["source"]["uidValidity"]
    )
    if (
        not parsed["seen"]
        or parsed["year"] != action["year"]
        or (not allowDeleted and "\\deleted" in {f.lower() for f in parsed["flags"]})
    ):
        raise ImapExecutionBlocked("stale-source")


def _select(client: Any, folder: str, writable: bool = False) -> None:
    _ok(client.select(_pathQuote(folder), readonly=not writable))


def _responseNumber(client: Any, name: str) -> str:
    _, rows = client.response(name)
    if (
        not rows
        or len(rows) != 1
        or not isinstance(rows[0], bytes)
        or not rows[0].isdigit()
        or not 0 < int(rows[0]) <= 4294967295
    ):
        raise ImapExecutionBlocked("environment-untrusted")
    return str(int(rows[0]))


def _ok(response: tuple) -> list:
    status, rows = response
    if status != "OK":
        raise ImapExecutionBlocked("verification-failed")
    return rows
