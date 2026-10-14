"""Execute one approved IMAP-to-local Thunderbird archive action safely."""

import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import Any, Callable

from mailAgent.executionJournal import (
    executionJournalFinish,
    executionJournalLoad,
    executionJournalPath,
    executionJournalRegister,
    executionJournalRetry,
    executionJournalStart,
)
from mailAgent.executionPlan import executionPlanBuild
from mailAgent.imapExecution import (
    ImapExecutionBlocked,
    _responseOk,
    _sourceRead,
    _sourceValidate,
)
from mailAgent.localArchiveExecution import (
    LocalArchiveExecutionBlocked,
    localArchiveContains,
    localArchiveCopyVerify,
    localArchiveDigestVerify,
)


def localArchiveFileExecute(
    client: Any,
    approved: dict,
    config: dict,
    currentObserve: Callable[[], dict],
    actionId: str,
    *,
    confirm: bool = False,
    path: Path | None = None,
) -> dict:
    """Archive exactly one approved old Inbox message and remove its IMAP source."""
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
        return _localFileExecute(
            client, approved, config, currentObserve, actionId, selected
        )
    finally:
        os.close(descriptor)


def _localFileExecute(
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

    capabilities = {
        value.decode().upper() if isinstance(value, bytes) else str(value).upper()
        for value in client.capabilities
    }
    if "UIDPLUS" not in capabilities:
        raise ImapExecutionBlocked("unsupported")

    proof = _proofRead(path, actionId)
    try:
        source = _sourceRead(client, action)
        fresh = any(candidate["actionId"] == actionId for candidate in result["actions"])

        if source is None:
            if not proof or not proof["removing"]:
                raise ImapExecutionBlocked("stale-source")
            if not localArchiveDigestVerify(action, proof["archiveDigest"]):
                raise ImapExecutionBlocked("verification-failed")
            _recordResume(actionId, record, path)
            executionJournalFinish(
                actionId,
                "completed",
                verification="local-archive-and-removal-verified",
                path=path,
            )
            return _recordRead(actionId, path)

        if not fresh:
            raise ImapExecutionBlocked("stale-source")
        _sourceValidate(source, action, allowDeleted=bool(proof and proof["removing"]))
        sourceDigest = sha256(source[1]).hexdigest()

        if proof is not None:
            if sourceDigest != proof["sourceDigest"]:
                raise ImapExecutionBlocked("stale-source")
            if proof["path"] != action["destination"]["path"]:
                raise ImapExecutionBlocked("destination-changed")
            if not localArchiveDigestVerify(action, proof["archiveDigest"]):
                raise ImapExecutionBlocked("verification-failed")
            _recordResume(actionId, record, path)
        else:
            if record["state"] in ("blocked", "failed"):
                # Reconcile whether an earlier uncheckpointed copy exists before retry.
                localArchiveContains(source[1], action)
                executionJournalRetry(
                    actionId,
                    revalidated=True,
                    partialOutcomeVerified=True,
                    path=path,
                )
                record = _recordRead(actionId, path)
            if record["startedAt"] is None:
                executionJournalStart(actionId, revalidated=True, path=path)
            copied = localArchiveCopyVerify(source[1], action)
            proof = dict(
                sourceDigest=sourceDigest,
                archiveDigest=copied["digest"],
                path=copied["path"],
                removing=False,
            )
            _proofWrite(path, actionId, proof)

        if not localArchiveDigestVerify(action, proof["archiveDigest"]):
            raise ImapExecutionBlocked("verification-failed")

        if not proof["removing"]:
            proof = dict(proof, removing=True)
            _proofWrite(path, actionId, proof)
        _sourceRemoveExact(client, action, proof)

        if _sourceRead(client, action) is not None:
            raise ImapExecutionBlocked("verification-failed")
        if not localArchiveDigestVerify(action, proof["archiveDigest"]):
            raise ImapExecutionBlocked("verification-failed")
        executionJournalFinish(
            actionId,
            "completed",
            verification="local-archive-and-removal-verified",
            path=path,
        )
    except LocalArchiveExecutionBlocked as error:
        converted = ImapExecutionBlocked(str(error))
        _failureRecord(actionId, converted, path)
        raise converted from error
    except Exception as error:
        _failureRecord(actionId, error, path)
        raise
    return _recordRead(actionId, path)


def _actionSelect(
    approved: dict,
    config: dict,
    observe: Callable[[], dict],
    actionId: str,
) -> tuple[dict, dict]:
    result = executionPlanBuild(approved, config, observe())
    candidates = result["actions"] + [
        entry["action"] for entry in result["blocked"] if "action" in entry
    ]
    matches = [action for action in candidates if action["actionId"] == actionId]
    if len(matches) != 1:
        raise ImapExecutionBlocked("unapproved")
    action = matches[0]
    sourceAccount = next(
        account
        for account in config["mailboxes"]
        if account["id"] == action["source"]["mailbox"]
    )
    if (
        action["disposition"] != "file"
        or action["destination"]["kind"] != "local"
        or action["destination"]["format"] != "thunderbird"
        or sourceAccount["role"] != "personal"
        or action["destination"]["mailbox"] != sourceAccount["id"]
        or type(action["year"]) is not int
        or action["year"] >= config["general"]["liveYear"]
        or action.get("requiresFolderCreation")
    ):
        raise ImapExecutionBlocked("unsupported")
    return action, result


def _sourceRemoveExact(client: Any, action: dict, proof: dict) -> None:
    source = _sourceRead(client, action, writable=True)
    if source is None:
        if proof["removing"]:
            return
        raise ImapExecutionBlocked("stale-source")
    _sourceValidate(source, action, allowDeleted=proof["removing"])
    if sha256(source[1]).hexdigest() != proof["sourceDigest"]:
        raise ImapExecutionBlocked("stale-source")
    uid = action["source"]["uid"]
    _responseOk(client.uid("STORE", uid, "+FLAGS.SILENT", r"(\Deleted)"))
    _responseOk(client.uid("EXPUNGE", uid))


def _recordResume(actionId: str, record: dict, path: Path) -> None:
    if record["state"] in ("blocked", "failed"):
        executionJournalRetry(
            actionId,
            revalidated=True,
            partialOutcomeVerified=True,
            path=path,
        )
        record = _recordRead(actionId, path)
    if record["state"] == "pending" and record["startedAt"] is None:
        executionJournalStart(actionId, revalidated=True, path=path)


def _failureRecord(actionId: str, error: Exception, path: Path) -> None:
    latest = _recordRead(actionId, path)
    if latest["state"] != "pending":
        return
    executionJournalFinish(
        actionId,
        "blocked" if isinstance(error, ImapExecutionBlocked) and latest["startedAt"] is None else "failed",
        error=(str(error) if isinstance(error, ImapExecutionBlocked) else "network-failure"),
        path=path,
    )


def _recordRead(actionId: str, path: Path) -> dict:
    return next(
        record
        for record in executionJournalLoad(path)
        if record["action"]["actionId"] == actionId
    )


def _proofRead(path: Path, actionId: str) -> dict | None:
    executionJournalLoad(path)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS local_copy_proofs (action_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        row = db.execute(
            "SELECT payload FROM local_copy_proofs WHERE action_id=?", (actionId,)
        ).fetchone()
        db.commit()
    if row is None:
        return None
    proof = json.loads(row[0])
    _proofValidate(proof)
    return proof


def _proofWrite(path: Path, actionId: str, proof: dict) -> None:
    _proofValidate(proof)
    existing = _proofRead(path, actionId)
    if existing and (
        any(existing[key] != proof[key] for key in proof if key != "removing")
        or (existing["removing"] and not proof["removing"])
    ):
        raise ValueError("Local archive proof is immutable")
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT OR REPLACE INTO local_copy_proofs(action_id, payload) VALUES (?, ?)",
            (actionId, json.dumps(proof, sort_keys=True, separators=(",", ":"))),
        )
        db.commit()


def _proofValidate(proof: dict) -> None:
    if set(proof) != {"sourceDigest", "archiveDigest", "path", "removing"}:
        raise ValueError("Invalid local archive proof")
    if (
        type(proof["removing"]) is not bool
        or not isinstance(proof["path"], str)
        or not Path(proof["path"]).is_absolute()
        or any(
            not isinstance(proof[key], str)
            or len(proof[key]) != 64
            or any(char not in "0123456789abcdef" for char in proof[key])
            for key in ("sourceDigest", "archiveDigest")
        )
    ):
        raise ValueError("Invalid local archive proof")
