"""Tests for verified local Thunderbird archive copying."""

import mailbox
from pathlib import Path

import pytest

from mailAgent.executionPlan import executionActionId
from mailAgent.localArchiveExecution import (
    LocalArchiveExecutionBlocked,
    localArchiveContains,
    localArchiveCopyVerify,
)


SOURCE = (
    b"Date: Mon, 1 Jan 2024 10:00:00 +0000\r\n"
    b"From: sender@example.com\r\n"
    b"To: user@example.com\r\n"
    b"Subject: Archive test\r\n"
    b"Message-ID: <archive-test@example.com>\r\n"
    b"\r\n"
    b"Hello\r\n"
    b"From body line\r\n"
)


def actionBuild(path: Path) -> dict:
    action = dict(
        source=dict(
            mailbox="andy",
            folder="INBOX",
            uidValidity="123",
            uid="456",
            seen=True,
        ),
        disposition="file",
        readState="read",
        year=2024,
        decisionSource="sender",
        configFingerprint="a" * 64,
        folderCreationApproved=False,
        canonical="Finance/PayPal",
        destination=dict(
            kind="local",
            mailbox="andy",
            folder="Finance/PayPal",
            path=str(path),
            format="thunderbird",
        ),
        requiresFolderCreation=False,
    )
    action["actionId"] = executionActionId(action)
    action.update(approved=True, executionPermitted=True)
    return action


def mboxCreate(path: Path) -> None:
    box = mailbox.mbox(path, create=True)
    box.close()


def testCopyVerifyStoresOneMessageAndIsIdempotent(tmp_path):
    path = tmp_path / "PayPal"
    mboxCreate(path)
    action = actionBuild(path)

    first = localArchiveCopyVerify(SOURCE, action)
    second = localArchiveCopyVerify(SOURCE, action)

    assert first["state"] == "destination-verified"
    assert second["digest"] == first["digest"]
    assert localArchiveContains(SOURCE, action)
    box = mailbox.mbox(path, create=False)
    try:
        assert len(box) == 1
        stored = box.get_bytes(next(box.iterkeys()), from_=False)
        assert b">From body line" in stored
    finally:
        box.close()


def testCopyRejectsMissingDestination(tmp_path):
    action = actionBuild(tmp_path / "missing")
    with pytest.raises(LocalArchiveExecutionBlocked, match="destination-changed"):
        localArchiveCopyVerify(SOURCE, action)


def testCopyRejectsSymlinkDestination(tmp_path):
    target = tmp_path / "target"
    mboxCreate(target)
    link = tmp_path / "link"
    link.symlink_to(target)
    action = actionBuild(link)
    with pytest.raises(LocalArchiveExecutionBlocked, match="destination-changed"):
        localArchiveCopyVerify(SOURCE, action)


def testDuplicateVerifiedCopiesBlock(tmp_path):
    path = tmp_path / "PayPal"
    mboxCreate(path)
    action = actionBuild(path)
    box = mailbox.mbox(path, create=False)
    try:
        box.add(SOURCE)
        box.add(SOURCE)
        box.flush()
    finally:
        box.close()

    with pytest.raises(LocalArchiveExecutionBlocked, match="verification-failed"):
        localArchiveContains(SOURCE, action)


def testCopyRejectsFolderCreationRequest(tmp_path):
    path = tmp_path / "PayPal"
    mboxCreate(path)
    action = actionBuild(path)
    action["requiresFolderCreation"] = True
    action["folderCreationApproved"] = True
    action["actionId"] = executionActionId(action)

    with pytest.raises(LocalArchiveExecutionBlocked, match="unsupported"):
        localArchiveCopyVerify(SOURCE, action)
