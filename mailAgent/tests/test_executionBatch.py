"""Bulk execution preserves explicit review and per-action revalidation."""

import pytest

from mailAgent.executionBatch import executionBatchRun


def review(*actionIds):
    return {
        "candidates": [
            {"actionId": actionId, "batchId": f"batch-{actionId}"}
            for actionId in actionIds
        ]
    }


class LogCapture:
    def __init__(self):
        self.infoMessages = []
        self.errorMessages = []

    def info(self, message):
        self.infoMessages.append(message)

    def error(self, message):
        self.errorMessages.append(message)


def testBulkExecutesCapturedActionsInOrderWithFreshReview():
    initial = review("a", "b")
    refreshed = [review("a", "b", "new"), review("b", "new")]
    calls = []

    def refresh():
        calls.append(("refresh", None))
        return refreshed.pop(0)

    def execute(actionId, fresh):
        calls.append(("execute", actionId, [c["actionId"] for c in fresh["candidates"]]))
        return {"state": "completed"}

    result = executionBatchRun(initial, refresh, execute)

    assert result == {"state": "completed", "completed": 2, "requested": 2}
    assert calls == [
        ("refresh", None),
        ("execute", "a", ["a", "b", "new"]),
        ("refresh", None),
        ("execute", "b", ["b", "new"]),
    ]


def testBulkUsesFreshActionIdWhenStableIntentRemains():
    initial = {"candidates": [{"actionId": "before", "batchId": "stable"}]}
    fresh = {"candidates": [{"actionId": "after", "batchId": "stable"}]}
    executed = []

    result = executionBatchRun(
        initial,
        lambda: fresh,
        lambda actionId, current: executed.append(actionId) or {"state": "completed"},
    )

    assert result == {"state": "completed", "completed": 1, "requested": 1}
    assert executed == ["after"]


def testBulkReportsInitialAndCompletedProgress():
    updates = []

    result = executionBatchRun(
        review("a", "b"),
        lambda: review("a", "b"),
        lambda actionId, fresh: {"state": "completed"},
        progress=lambda completed, requested: updates.append((completed, requested)),
    )

    assert result == {"state": "completed", "completed": 2, "requested": 2}
    assert updates == [(0, 2), (1, 2), (2, 2)]


def testBulkLogsVerifiedSubjectAndHumanDestination():
    candidate = {
        "actionId": "a",
        "batchId": "batch-a",
        "subject": "Your Apple\nreceipt",
        "canonical": "Software & Web/Apple",
        "sender": "no_reply@email.apple.com",
        "mailbox": "kathy",
        "uid": "7475",
    }
    selected = {"candidates": [candidate]}
    logger = LogCapture()

    result = executionBatchRun(
        selected,
        lambda: selected,
        lambda actionId, fresh: {"state": "completed"},
        logger=logger,
    )

    assert result == {"state": "completed", "completed": 1, "requested": 1}
    assert "Mail Your Apple receipt moved to Software & Web/Apple" in logger.infoMessages


def testBulkDoesNotLogMoveWhenExecutionDoesNotComplete():
    candidate = {
        "actionId": "a",
        "batchId": "batch-a",
        "subject": "Statement",
        "canonical": "Finance/Banking",
    }
    selected = {"candidates": [candidate]}
    logger = LogCapture()

    with pytest.raises(ValueError, match="did not complete"):
        executionBatchRun(
            selected,
            lambda: selected,
            lambda actionId, fresh: {"state": "blocked"},
            logger=logger,
        )

    assert "Mail Statement moved to Finance/Banking" not in logger.infoMessages


def testBulkStopsWhenReviewedActionDisappears():
    executed = []

    def execute(actionId, fresh):
        executed.append(actionId)
        return {"state": "completed"}

    with pytest.raises(ValueError, match="changed or is no longer executable"):
        executionBatchRun(review("a", "b"), lambda: review("a"), execute)

    assert executed == ["a"]


def testBulkStopsWhenExecutionDoesNotComplete():
    with pytest.raises(ValueError, match="did not complete"):
        executionBatchRun(
            review("a"),
            lambda: review("a"),
            lambda actionId, fresh: {"state": "blocked"},
        )


def testBulkRejectsDuplicateReviewedActionIds():
    duplicate = {
        "candidates": [
            {"actionId": "a", "batchId": "same"},
            {"actionId": "b", "batchId": "same"},
        ]
    }
    with pytest.raises(ValueError, match="unique reviewed actions"):
        executionBatchRun(duplicate, lambda: duplicate, lambda *_: None)


def testEmptyBulkIsACompletedNoOp():
    assert executionBatchRun(review(), lambda: review(), lambda *_: None) == {
        "state": "completed",
        "completed": 0,
        "requested": 0,
    }
