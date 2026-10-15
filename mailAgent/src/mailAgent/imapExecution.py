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
    logger=None,
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
            client, approved, config, currentObserve, actionId, selected, logger
        )
    finally:
        os.close(descriptor)


def imapFolderEnsure(client: Any, action: dict, logger=None) -> bool:
    """Create only the exact approved path; return whether it was created."""
    action = executionActionValidate(action)
    if action["disposition"] != "file" or action["destination"]["kind"] != "imap":
        raise ImapExecutionBlocked("unsupported")
    folder = action["destination"]["folder"]
    if _folderExists(client, folder):
        return False
    if not action["folderCreationApproved"]:
        raise ImapExecutionBlocked("unapproved")
    # A failed CREATE may race another creator. Re-observe the exact path.
    client.create(_pathQuote(folder))
    if not _folderExists(client, folder):
        raise ImapExecutionBlocked("destination-changed")
    if logger is not None:
        logger.info(
            f'Mailbox created: {action["source"]["mailbox"]} -> {folder}'
        )
    return True


## workflow


def _fileExecute(
    client: Any,
    approved: dict,
    config: dict,
    observe: Callable[[], dict],
    actionId: str,
    path: Path,
    logger=None,
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
            proof = _copyStart(client, action, source, path, logger)
        _destinationVerify(client, action, proof)
        proof = _sourceRemove(client, action, proof, path)
        if _sourceRead(client, action) is not None:
            raise ImapExecutionBlocked("verification-failed")
        _destinationVerify(client, action, proof)
        executionJournalFinish(
            actionId, "completed", verification="destination-verified", path=path
        )
        if logger is not None:
            sourceId = action["source"]
            destination = action["destination"]
            logger.info(
                "Mail moved: "
                f'{sourceId["mailbox"]}:{sourceId["folder"]} '
                f'UID {sourceId["uid"]} -> {destination["folder"]}'
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
    client: Any,
    action: dict,
    source: tuple[bytes, bytes],
    path: Path,
    logger=None,
) -> dict:
    actionId = action["actionId"]
    imapFolderEnsure(client, action, logger=logger)
    _folderSelect(client, action["destination"]["folder"])
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
    _responseOk(
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
        _responseOk(client.uid("STORE", uid, "+FLAGS.SILENT", r"(\Deleted)"))
        _responseOk(client.uid("EXPUNGE", uid))
    elif not proof["removing"]:
        raise ImapExecutionBlocked("stale-source")
    return proof


## probes


def _destinationVerify(client: Any, action: dict, proof: dict) -> None:
    folder = action["destination"]["folder"]
    _folderSelect(client, folder)
    if _responseNumber(client, "UIDVALIDITY") != proof["uidValidity"]:
        raise ImapExecutionBlocked("destination-changed")
    rows = _uidSearch(client, proof["uidNext"])
    matches = []
    for uid in rows:
        fetched = _uidFetch(client, uid)
        if fetched is not None and sha256(fetched[1]).hexdigest() == proof["digest"]:
            matches.append(uid)
    if len(matches) != 1:
        raise ImapExecutionBlocked("verification-failed")


def _sourceRead(client: Any, action: dict, writable: bool = False):
    _folderSelect(client, action["source"]["folder"], readonly=not writable)
    return _uidFetch(client, action["source"]["uid"])


def _sourceValidate(source: tuple[bytes, bytes], action: dict, allowDeleted=False) -> None:
    flags, body = source
    parsed = messageParse(body)
    if not parsed.get("seen"):
        raise ImapExecutionBlocked("stale-source")
    deleted = b"\\Deleted" in flags or b"\\deleted" in flags.lower()
    if deleted and not allowDeleted:
        raise ImapExecutionBlocked("stale-source")


def _folderExists(client: Any, folder: str) -> bool:
    status, rows = client.list()
    if status != "OK":
        raise ImapExecutionBlocked("environment-untrusted")
    matches = []
    for row in rows or []:
        parsed = folderParse(row)
        if parsed and parsed["path"] == folder:
            matches.append(parsed)
    if len(matches) > 1:
        raise ImapExecutionBlocked("destination-changed")
    if not matches:
        return False
    if "\\noselect" in {flag.lower() for flag in matches[0].get("attributes", [])}:
        raise ImapExecutionBlocked("destination-changed")
    return True


def _folderSelect(client: Any, folder: str, readonly: bool = True) -> None:
    _responseOk(client.select(_pathQuote(folder), readonly=readonly))


def _uidFetch(client: Any, uid: str):
    status, rows = client.uid("FETCH", uid, "(UID FLAGS BODY.PEEK[])")
    if status != "OK":
        raise ImapExecutionBlocked("environment-untrusted")
    if not rows or rows == [None]:
        return None
    body = None
    flags = b""
    for row in rows:
        if isinstance(row, tuple) and len(row) == 2:
            flags, body = row
    if body is None:
        return None
    return flags, body


def _uidSearch(client: Any, start: str) -> list[str]:
    status, rows = client.uid("SEARCH", None, f"UID {start}:*")
    if status != "OK" or len(rows or []) != 1:
        raise ImapExecutionBlocked("environment-untrusted")
    return [value.decode() for value in rows[0].split()]


def _responseNumber(client: Any, name: str) -> str:
    _, rows = client.response(name)
    if not rows or len(rows) != 1:
        raise ImapExecutionBlocked("environment-untrusted")
    value = rows[0]
    if not isinstance(value, bytes) or not value.isdigit():
        raise ImapExecutionBlocked("environment-untrusted")
    return str(int(value))


def _responseOk(response) -> None:
    status = response[0] if isinstance(response, tuple) else response
    if status != "OK":
        raise ImapExecutionBlocked("environment-untrusted")
