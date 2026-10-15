"""Sequential bulk execution over an explicitly reviewed candidate set."""


def executionBatchRun(
    review: dict,
    reviewRefresh,
    execute,
    progress=None,
    logger=None,
) -> dict:
    """Execute the currently reviewed candidates one at a time with revalidation.

    The candidate set is captured at button press. Before every mutation the review
    is rebuilt and the same reviewed intent must still be executable. Newly appearing
    candidates are never added to the running batch. A destination folder changing
    from missing to existing is allowed because that is an expected idempotent effect
    of an earlier action in the same batch. Other intent changes stop the batch.
    """
    candidates = list(review.get("candidates", []))
    batchIds = [candidate["batchId"] for candidate in candidates]
    if len(batchIds) != len(set(batchIds)):
        raise ValueError("Bulk execution requires unique reviewed actions")

    requested = len(batchIds)
    completed = 0
    original = {candidate["batchId"]: candidate for candidate in candidates}
    if logger is not None:
        logger.info(f"Bulk mail execution started: {requested} reviewed messages")
    if progress is not None:
        progress(completed, requested)

    for index, batchId in enumerate(batchIds, start=1):
        intended = original[batchId]
        if logger is not None:
            logger.info(_candidateLog("Mail move preparing", intended, index, requested))

        fresh = reviewRefresh()
        matches = [
            candidate
            for candidate in fresh.get("candidates", [])
            if candidate.get("batchId") == batchId
        ]
        if len(matches) != 1:
            message = (
                "Bulk execution stopped because a reviewed action changed or is no longer executable"
            )
            if logger is not None:
                logger.error(_candidateLog("Mail move blocked", intended, index, requested))
            raise ValueError(message)

        current = matches[0]
        actionId = current["actionId"]
        result = execute(actionId, fresh)
        if not isinstance(result, dict) or result.get("state") != "completed":
            if logger is not None:
                logger.error(_candidateLog("Mail move did not complete", current, index, requested))
            raise ValueError("Bulk execution stopped because an action did not complete")

        completed += 1
        if logger is not None:
            logger.info(_successLog(current))
        if progress is not None:
            progress(completed, requested)

    if logger is not None:
        logger.info(f"Bulk mail execution completed: {completed}/{requested} messages")
    return dict(state="completed", completed=completed, requested=requested)


def _candidateLog(prefix: str, candidate: dict, index: int, requested: int) -> str:
    """Return useful movement context for preparation and failure diagnostics."""
    sender = candidate.get("sender") or candidate.get("domain") or "unknown sender"
    mailbox = candidate.get("mailbox", "unknown mailbox")
    uid = candidate.get("uid", "?")
    destination = candidate.get("canonical") or candidate.get("destination") or "unknown"
    return (
        f"{prefix} {index}/{requested}: mailbox={mailbox} source=INBOX UID={uid} "
        f"sender={sender} destination={destination}"
    )


def _successLog(candidate: dict) -> str:
    """Return a concise, human-readable message only after verified completion."""
    subject = _logText(candidate.get("subject"), "(no subject)")
    destination = _logText(
        candidate.get("canonical") or candidate.get("destination"), "unknown destination"
    )
    return f"Mail {subject} moved to {destination}"


def _logText(value, fallback: str) -> str:
    """Collapse control whitespace so message metadata cannot create fake log lines."""
    if value is None:
        return fallback
    text = " ".join(str(value).split())
    return text or fallback
