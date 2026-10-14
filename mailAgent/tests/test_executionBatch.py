"""Bulk execution preserves explicit review and per-action revalidation."""

import pytest

from mailAgent.executionBatch import executionBatchRun


def review(*actionIds):
    return {"candidates": [{"actionId": actionId} for actionId in actionIds]}


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
    with pytest.raises(ValueError, match="unique reviewed actions"):
        executionBatchRun(review("a", "a"), lambda: review("a"), lambda *_: None)


def testEmptyBulkIsACompletedNoOp():
    assert executionBatchRun(review(), lambda: review(), lambda *_: None) == {
        "state": "completed",
        "completed": 0,
        "requested": 0,
    }
