"""Transactional execution state and audit history, independent of mailbox APIs."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterator

from mailAgent.executionPlan import executionActionValidate

_STATES = {"pending", "completed", "blocked", "failed"}
_VERIFICATION = {
    "file": {"destination-verified", "local-archive-and-removal-verified"},
    "ignore": {"ignore-honoured"},
    "junk": {"junk-state-verified"},
}
_ERRORS = {
    "stale-source",
    "destination-changed",
    "unapproved",
    "unsupported",
    "verification-failed",
    "network-failure",
    "interrupted",
    "environment-untrusted",
}

## journal


def executionJournalCompleted(path: Path | None = None) -> set[str]:
    """Return completed action IDs without creating a missing journal."""
    return {
        entry["action"]["actionId"]
        for entry in executionJournalLoad(path)
        if entry["state"] == "completed"
    }


def executionJournalHistory(actionId: str, path: Path | None = None) -> list[dict]:
    """Return the immutable ordered history for one known action."""
    selected = path or executionJournalPath()
    if not selected.exists():
        raise ValueError("Unknown execution action")
    with _database(selected) as db:
        _recordGet(db, actionId)
        return [
            dict(row)
            for row in db.execute(
                "SELECT timestamp, state, verification, error FROM events WHERE action_id=? ORDER BY sequence",
                (actionId,),
            )
        ]


def executionJournalLoad(path: Path | None = None) -> list[dict]:
    """Load state; started pending actions require verification before retry."""
    selected = path or executionJournalPath()
    if selected.is_symlink():
        raise ValueError("Journal must not be a symbolic link")
    if not selected.exists():
        return []
    with _database(selected) as db:
        return [
            _recordDecode(row)
            for row in db.execute("SELECT * FROM actions ORDER BY action_id")
        ]


def executionJournalPath() -> Path:
    """Return user state storage for execution, separate from preferences."""
    return Path.home() / ".local/state/mailAgent/execution.sqlite3"


def executionJournalRegister(actions: list[dict], path: Path | None = None) -> None:
    """Atomically register approved identities; repeat registration preserves state.

    A different action for the same source is rejected, even after completion.
    An engine must explicitly reconcile such changes rather than copy twice.
    """
    sanitized = [executionActionValidate(action) for action in actions]
    with _database(path or executionJournalPath()) as db:
        for action in sanitized:
            actionId = action["actionId"]
            sourceKey = _sourceKey(action)
            prior = db.execute(
                "SELECT action_id FROM actions WHERE source_key = ?", (sourceKey,)
            ).fetchone()
            if prior and prior[0] != actionId:
                raise ValueError("Conflicting execution action for source")
            payload = _json(action)
            existing = db.execute(
                "SELECT payload FROM actions WHERE action_id = ?", (actionId,)
            ).fetchone()
            if existing:
                if existing[0] != payload:
                    raise ValueError("Execution action identity changed")
                continue
            db.execute(
                "INSERT INTO actions(action_id, source_key, payload, state, attempts) VALUES (?, ?, ?, 'pending', 0)",
                (actionId, sourceKey, payload),
            )
            _event(db, actionId, "pending", None, None)


def executionJournalRetry(
    actionId: str,
    *,
    revalidated: bool,
    partialOutcomeVerified: bool,
    path: Path | None = None,
) -> None:
    """Release interrupted/failed/blocked state only after fresh reconciliation.

    These facts must come from future read-only probes, never an automatic retry.
    Completed actions are immutable. Audit history retains every earlier attempt.
    """
    if revalidated is not True or partialOutcomeVerified is not True:
        raise ValueError("Retry requires revalidation and partial-outcome verification")
    with _database(path or executionJournalPath()) as db:
        row = _recordGet(db, actionId)
        if row["state"] == "completed" or (
            row["state"] == "pending" and row["started_at"] is None
        ):
            raise ValueError("Action does not need retry")
        db.execute(
            "UPDATE actions SET state='pending', started_at=NULL, finished_at=NULL, verification=NULL, error=NULL WHERE action_id=?",
            (actionId,),
        )
        _event(db, actionId, "pending", None, None)


def executionJournalStart(
    actionId: str, *, revalidated: bool, path: Path | None = None
) -> None:
    """Durably mark an attempt before a future primitive can run."""
    if revalidated is not True:
        raise ValueError("Start requires fresh validation")
    with _database(path or executionJournalPath()) as db:
        row = _recordGet(db, actionId)
        if row["state"] != "pending" or row["started_at"] is not None:
            raise ValueError(
                "Action is completed or requires reconciliation before start"
            )
        db.execute(
            "UPDATE actions SET started_at=?, attempts=attempts+1 WHERE action_id=?",
            (_now(), actionId),
        )
        _event(db, actionId, "started", None, None)


def executionJournalFinish(
    actionId: str,
    state: str,
    *,
    verification: str | None = None,
    error: str | None = None,
    path: Path | None = None,
) -> None:
    """Persist verified completion or a fixed safe failure code, never bodies/errors."""
    if state not in _STATES - {"pending"}:
        raise ValueError("Invalid terminal journal state")
    with _database(path or executionJournalPath()) as db:
        row = _recordGet(db, actionId)
        action = executionActionValidate(json.loads(row["payload"]))
        if state == "completed":
            allowed = _verificationAllowed(action)
            if verification not in allowed or error is not None:
                raise ValueError("Completion requires matching verification")
        elif error not in _ERRORS or verification is not None:
            raise ValueError("Failure requires a safe error code")
        if row["state"] == "completed":
            if state == "completed" and row["verification"] == verification:
                return
            raise ValueError("Completed action is immutable")
        if row["state"] != "pending" or (
            state != "blocked" and row["started_at"] is None
        ):
            raise ValueError("Action must be pending and started")
        db.execute(
            "UPDATE actions SET state=?, finished_at=?, verification=?, error=? WHERE action_id=?",
            (state, _now(), verification, error, actionId),
        )
        _event(db, actionId, state, verification, error)


## storage


@contextmanager
def _database(path: Path) -> Iterator[sqlite3.Connection]:
    if path.is_symlink():
        raise ValueError("Journal must not be a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    created = False
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        created = True
    except FileExistsError:
        if not path.is_file() or path.stat().st_mode & 0o077:
            raise ValueError("Journal must be a user-only regular file")
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA synchronous=FULL")
        if created:
            db.execute("BEGIN IMMEDIATE")
            db.execute("PRAGMA user_version=1")
            db.execute(
                "CREATE TABLE actions (action_id TEXT PRIMARY KEY, source_key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL, started_at TEXT, finished_at TEXT, verification TEXT, error TEXT, attempts INTEGER NOT NULL)"
            )
            db.execute(
                "CREATE TABLE events (sequence INTEGER PRIMARY KEY, action_id TEXT NOT NULL, timestamp TEXT NOT NULL, state TEXT NOT NULL, verification TEXT, error TEXT)"
            )
            db.commit()
        db.execute("BEGIN IMMEDIATE")
        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ValueError("Unsupported execution journal schema")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _event(
    db: sqlite3.Connection,
    actionId: str,
    state: str,
    verification: str | None,
    error: str | None,
) -> None:
    db.execute(
        "INSERT INTO events(action_id, timestamp, state, verification, error) VALUES (?, ?, ?, ?, ?)",
        (actionId, _now(), state, verification, error),
    )


def _recordDecode(row: sqlite3.Row) -> dict:
    action = executionActionValidate(json.loads(row["payload"]))
    if (
        action["actionId"] != row["action_id"]
        or row["state"] not in _STATES
        or _sourceKey(action) != row["source_key"]
    ):
        raise ValueError("Corrupt execution journal record")
    if row["state"] == "completed" and row["verification"] not in _verificationAllowed(
        action
    ):
        raise ValueError("Unverified completion in journal")
    return dict(
        action=action,
        state=row["state"],
        startedAt=row["started_at"],
        finishedAt=row["finished_at"],
        verification=row["verification"],
        error=row["error"],
        attempts=row["attempts"],
        requiresVerification=row["started_at"] is not None
        and row["state"] != "completed",
    )


def _recordGet(db: sqlite3.Connection, actionId: str) -> sqlite3.Row:
    row = db.execute("SELECT * FROM actions WHERE action_id=?", (actionId,)).fetchone()
    if row is None:
        raise ValueError("Unknown execution action")
    _recordDecode(row)
    return row


def _sourceKey(action: dict) -> str:
    source = action["source"]
    return _json([source[key] for key in ("mailbox", "folder", "uidValidity", "uid")])


def _verificationAllowed(action: dict) -> set[str]:
    if action["disposition"] == "file":
        return {
            (
                "local-archive-and-removal-verified"
                if action["destination"]["kind"] == "local"
                else "destination-verified"
            )
        }
    return _VERIFICATION[action["disposition"]]


def _json(value: dict | list) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
