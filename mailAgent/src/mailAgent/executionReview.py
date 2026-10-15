"""Build explicit single-message execution choices from the current filing plan."""

from copy import deepcopy

from mailAgent.executionPlan import (
    executionActionId,
    executionPlanBuild,
    executionPlanPrepare,
)


def executionReviewBuild(
    filingPlan: dict,
    config: dict,
    journalEntries: list[dict] | None = None,
) -> dict:
    """Return executable live-year IMAP File actions plus verified completed moves."""
    current = executionPlanPrepare(filingPlan, config)
    approved = deepcopy(current)
    approved["executionEnabled"] = True
    approved["entries"] = []
    liveYear = config["general"]["liveYear"]

    for entry in current["entries"]:
        destination = entry.get("destination")
        if (
            entry.get("disposition") != "file"
            or not isinstance(destination, dict)
            or destination.get("kind") != "imap"
            or entry.get("year") != liveYear
        ):
            continue
        selected = deepcopy(entry)
        selected.update(
            approved=True,
            executionPermitted=True,
            folderCreationApproved=bool(entry.get("requiresFolderCreation")),
        )
        selected["actionId"] = executionActionId(
            dict(selected, configFingerprint=current["configFingerprint"])
        )
        approved["entries"].append(selected)

    completedIds = {
        entry["action"]["actionId"]
        for entry in journalEntries or []
        if entry.get("state") == "completed"
        and isinstance(entry.get("action"), dict)
        and isinstance(entry["action"].get("actionId"), str)
    }
    result = executionPlanBuild(approved, config, current, completedIds)
    evidence = _filingEvidence(filingPlan)
    candidates = []
    for action in result["actions"]:
        source = action["source"]
        original = evidence.get(_sourceKey(source), {})
        originalSource = original.get("source", {})
        candidates.append(
            dict(
                actionId=action["actionId"],
                batchId=_batchIdentity(action),
                mailbox=source["mailbox"],
                uid=source["uid"],
                year=action["year"],
                sender=originalSource.get("sender", ""),
                subject=originalSource.get("subject", ""),
                domain=originalSource.get("domain", ""),
                canonical=action["canonical"],
                destination=action["destination"]["folder"],
                createFolder=bool(action.get("requiresFolderCreation")),
                status="Ready",
            )
        )
    moved = _movedRows(journalEntries or [], current["configFingerprint"], liveYear)
    return dict(
        schemaVersion=1,
        current=current,
        approved=approved,
        candidates=candidates,
        moved=moved,
        blocked=result["blocked"],
    )


def executionReviewSelect(review: dict, identity: str) -> tuple[str, dict]:
    """Return one exact approved envelope selected by full or unique ID prefix."""
    if not isinstance(identity, str) or len(identity.strip()) < 8:
        raise ValueError("Execution action ID must contain at least 8 characters")
    prefix = identity.strip().lower()
    matches = [
        candidate
        for candidate in review.get("candidates", [])
        if candidate["actionId"].startswith(prefix)
    ]
    if len(matches) != 1:
        raise ValueError("Execution action ID is missing or ambiguous")
    actionId = matches[0]["actionId"]
    approved = deepcopy(review["approved"])
    approved["entries"] = [
        entry for entry in approved["entries"] if entry.get("actionId") == actionId
    ]
    if len(approved["entries"]) != 1:
        raise ValueError("Execution approval could not be selected")
    return actionId, approved


def _batchIdentity(action: dict) -> str:
    """Return a stable reviewed intent while destination existence changes safely."""
    stable = dict(action)
    stable["folderCreationApproved"] = False
    return executionActionId(stable)


def _movedRows(entries: list[dict], fingerprint: str, liveYear: int) -> list[dict]:
    """Present only journal-verified live IMAP moves as Moved."""
    moved = []
    for entry in entries:
        action = entry.get("action")
        destination = action.get("destination") if isinstance(action, dict) else None
        if (
            entry.get("state") != "completed"
            or entry.get("verification") != "destination-verified"
            or not isinstance(action, dict)
            or action.get("configFingerprint") != fingerprint
            or action.get("disposition") != "file"
            or action.get("year") != liveYear
            or not isinstance(destination, dict)
            or destination.get("kind") != "imap"
        ):
            continue
        source = action.get("source", {})
        moved.append(
            dict(
                actionId=action["actionId"],
                batchId=_batchIdentity(action),
                mailbox=source.get("mailbox", ""),
                uid=source.get("uid", ""),
                year=action["year"],
                sender="",
                subject="",
                domain="",
                canonical=action["canonical"],
                destination=destination["folder"],
                createFolder=False,
                status="Moved",
            )
        )
    return sorted(
        moved,
        key=lambda row: (
            str(row["mailbox"]).casefold(),
            str(row["canonical"]).casefold(),
            str(row["actionId"]),
        ),
    )


def _filingEvidence(filingPlan: dict) -> dict:
    result = {}
    for entry in filingPlan.get("proposals", []) + filingPlan.get("dispositions", []):
        source = entry.get("source", {})
        try:
            result[_sourceKey(source)] = entry
        except KeyError:
            continue
    return result


def _sourceKey(source: dict) -> tuple[str, str, str, str]:
    return tuple(
        str(source[key]) for key in ("mailbox", "folder", "uidValidity", "uid")
    )
