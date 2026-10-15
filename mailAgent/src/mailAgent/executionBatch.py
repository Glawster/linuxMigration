"""Sequential bulk execution over an explicitly reviewed candidate set."""


def executionBatchRun(review: dict, reviewRefresh, execute, progress=None) -> dict:
    """Execute the currently reviewed candidates one at a time with revalidation.

    The candidate set is captured at button press. Before every mutation the review
    is rebuilt and the same reviewed intent must still be executable. Newly appearing
    candidates are never added to the running batch. A destination folder changing
    from missing to existing is allowed because that is an expected idempotent effect
    of an earlier action in the same batch. Other intent changes stop the batch.
    """
    batchIds = [candidate["batchId"] for candidate in review.get("candidates", [])]
    if len(batchIds) != len(set(batchIds)):
        raise ValueError("Bulk execution requires unique reviewed actions")

    requested = len(batchIds)
    completed = 0
    if progress is not None:
        progress(completed, requested)

    for batchId in batchIds:
        fresh = reviewRefresh()
        matches = [
            candidate
            for candidate in fresh.get("candidates", [])
            if candidate.get("batchId") == batchId
        ]
        if len(matches) != 1:
            raise ValueError(
                "Bulk execution stopped because a reviewed action changed or is no longer executable"
            )
        actionId = matches[0]["actionId"]
        result = execute(actionId, fresh)
        if not isinstance(result, dict) or result.get("state") != "completed":
            raise ValueError("Bulk execution stopped because an action did not complete")
        completed += 1
        if progress is not None:
            progress(completed, requested)

    return dict(state="completed", completed=completed, requested=requested)
