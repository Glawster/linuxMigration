"""Execution review exposes only explicit single-message live IMAP filing choices."""

from copy import deepcopy

import pytest

from mailAgent.executionReview import executionReviewBuild, executionReviewSelect


def _config(tmp_path) -> dict:
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
                passwordEnv="MAIL_PASSWORD",
            )
        ],
    )


def _filing() -> dict:
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
                    sender="shop@example.com",
                    domain="example.com",
                ),
                disposition="file",
                readState="read",
                year=2026,
                decisionSource="domain",
                canonical="Shopping/Example",
                destination=dict(
                    kind="imap",
                    mailbox="andy",
                    folder="Shopping.Example",
                    exists=False,
                ),
                requiresFolderCreation=True,
                executionPermitted=False,
                sourceRemovalAllowed=False,
            )
        ],
        dispositions=[],
    )


def testReviewShowsExecutableLiveFileAndExactCreation(tmp_path) -> None:
    config = _config(tmp_path)
    review = executionReviewBuild(_filing(), config)
    assert len(review["candidates"]) == 1
    candidate = review["candidates"][0]
    assert candidate["sender"] == "shop@example.com"
    assert candidate["canonical"] == "Shopping/Example"
    assert candidate["createFolder"] is True
    assert not review["blocked"]

    actionId, approved = executionReviewSelect(review, candidate["actionId"][:12])
    assert actionId == candidate["actionId"]
    assert approved["executionEnabled"] is True
    assert len(approved["entries"]) == 1
    entry = approved["entries"][0]
    assert entry["approved"] is True
    assert entry["executionPermitted"] is True
    assert entry["folderCreationApproved"] is True


def testReviewExcludesOldLocalFiling(tmp_path) -> None:
    config = _config(tmp_path)
    filing = _filing()
    entry = filing["proposals"][0]
    entry["year"] = 2025
    entry["destination"] = dict(
        kind="local",
        mailbox="andy",
        folder="Shopping/Example",
        path=str(tmp_path / "myMail" / "Shopping.sbd" / "Example"),
        format="thunderbird",
        exists=True,
    )
    entry["requiresFolderCreation"] = False
    assert executionReviewBuild(filing, config)["candidates"] == []


def testReviewSelectRejectsShortMissingAndAmbiguousIds(tmp_path) -> None:
    review = executionReviewBuild(_filing(), _config(tmp_path))
    with pytest.raises(ValueError, match="at least 8"):
        executionReviewSelect(review, "1234")
    with pytest.raises(ValueError, match="missing or ambiguous"):
        executionReviewSelect(review, "deadbeef")

    duplicate = deepcopy(review["candidates"][0])
    duplicate["actionId"] = review["candidates"][0]["actionId"][:8] + "f" * 56
    review["candidates"].append(duplicate)
    with pytest.raises(ValueError, match="missing or ambiguous"):
        executionReviewSelect(review, review["candidates"][0]["actionId"][:8])
