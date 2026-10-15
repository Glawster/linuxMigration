"""Verified Thunderbird local-archive copy primitive.

This module deliberately does not remove the IMAP source. It provides the local
copy-and-verify half of REQ-010/MA-012 execution so orchestration can checkpoint
and revalidate before exact source removal.
"""

from email import policy
from email.generator import BytesGenerator
from email.parser import BytesParser
from hashlib import sha256
from io import BytesIO
import mailbox
from pathlib import Path
from typing import Any

from mailAgent.executionPlan import executionActionValidate


class LocalArchiveExecutionBlocked(ValueError):
    """A fixed safe reason for refusing a local archive operation."""


def localArchiveCopyVerify(source: bytes, action: dict) -> dict:
    """Copy one approved message to an existing Thunderbird mbox and verify it.

    The operation is idempotent for an already-present exact message. It never
    removes or changes the IMAP source and never creates archive folders.
    """
    approved = executionActionValidate(action)
    destination = approved.get("destination", {})
    if (
        approved.get("disposition") != "file"
        or destination.get("kind") != "local"
        or destination.get("format") != "thunderbird"
        or approved.get("requiresFolderCreation")
    ):
        raise LocalArchiveExecutionBlocked("unsupported")
    if not isinstance(source, bytes) or not source:
        raise LocalArchiveExecutionBlocked("verification-failed")

    path = Path(destination["path"])
    _destinationValidate(path)
    expected = _mboxBytes(source)
    digest = sha256(expected).hexdigest()

    box = mailbox.mbox(path, create=False)
    try:
        box.lock()
        matches = _matchingKeys(box, digest)
        if len(matches) > 1:
            raise LocalArchiveExecutionBlocked("verification-failed")
        if not matches:
            box.add(source)
            box.flush()
            matches = _matchingKeys(box, digest)
        if len(matches) != 1:
            raise LocalArchiveExecutionBlocked("verification-failed")
    except (mailbox.Error, OSError) as error:
        raise LocalArchiveExecutionBlocked("environment-untrusted") from error
    finally:
        try:
            box.unlock()
        finally:
            box.close()

    return dict(
        state="destination-verified",
        digest=digest,
        path=str(path),
        key=str(matches[0]),
    )


def localArchiveContains(source: bytes, action: dict) -> bool:
    """Return whether exactly one verified local copy exists; never mutate."""
    approved = executionActionValidate(action)
    destination = approved.get("destination", {})
    if (
        approved.get("disposition") != "file"
        or destination.get("kind") != "local"
        or destination.get("format") != "thunderbird"
    ):
        raise LocalArchiveExecutionBlocked("unsupported")
    return localArchiveDigestVerify(approved, sha256(_mboxBytes(source)).hexdigest())


def localArchiveDigestVerify(action: dict, digest: str) -> bool:
    """Verify exactly one archived message by a previously checkpointed digest."""
    approved = executionActionValidate(action)
    destination = approved.get("destination", {})
    if (
        approved.get("disposition") != "file"
        or destination.get("kind") != "local"
        or destination.get("format") != "thunderbird"
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
    ):
        raise LocalArchiveExecutionBlocked("unsupported")
    path = Path(destination["path"])
    _destinationValidate(path)
    box = mailbox.mbox(path, create=False)
    try:
        box.lock()
        matches = _matchingKeys(box, digest)
    except (mailbox.Error, OSError) as error:
        raise LocalArchiveExecutionBlocked("environment-untrusted") from error
    finally:
        try:
            box.unlock()
        finally:
            box.close()
    if len(matches) > 1:
        raise LocalArchiveExecutionBlocked("verification-failed")
    return len(matches) == 1


def _destinationValidate(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise LocalArchiveExecutionBlocked("destination-changed")
    if path.stat().st_mode & 0o002:
        raise LocalArchiveExecutionBlocked("environment-untrusted")


def _matchingKeys(box: mailbox.mbox, digest: str) -> list[Any]:
    matches = []
    for key in box.iterkeys():
        try:
            value = box.get_bytes(key, from_=False)
        except (KeyError, mailbox.Error, OSError) as error:
            raise LocalArchiveExecutionBlocked("verification-failed") from error
        if sha256(value).hexdigest() == digest:
            matches.append(key)
    return matches


def _mboxBytes(source: bytes) -> bytes:
    """Return the bytes Thunderbird/Python mbox storage should round-trip."""
    try:
        message = BytesParser(policy=policy.SMTP).parsebytes(source)
        output = BytesIO()
        BytesGenerator(output, policy=policy.SMTP, mangle_from_=True).flatten(message)
        return output.getvalue()
    except Exception as error:
        raise LocalArchiveExecutionBlocked("verification-failed") from error
