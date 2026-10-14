"""Sequential bulk execution over an explicitly reviewed candidate set."""


def executionBatchRun(review: dict, reviewRefresh, execute) -> dict:
    """Execute the currently reviewed candidates one at a time with revalidation.

    The candidate set is captured at button press. Before every mutation the review
    is rebuilt and the exact action id must still be executable. Newly appearing
    candidates are never added to the running batch. The batch stops immediately
    on a changed/blocked action or any execution failure.
    """
    actionIds = [candidate["actionId"] for candidate in review.get("candidates", [])]
    if len(actionIds) != len(set(actionIds)):
        raise ValueError("Bulk execution requires unique reviewed actions")

    completed = 0
    for actionId in actionIds:
        fresh = reviewRefresh()
        matches = [
            candidate
            for candidate in fresh.get("candidates", [])
            if candidate.get("actionId") == actionId
        ]
        if len(matches) != 1:
            raise ValueError(
                "Bulk execution stopped because a reviewed action changed or is no longer executable"
            )
        result = execute(actionId, fresh)
        if not isinstance(result, dict) or result.get("state") != "completed":
            raise ValueError("Bulk execution stopped because an action did not complete")
        completed += 1

    return dict(state="completed", completed=completed, requested=len(actionIds))
