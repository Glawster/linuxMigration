"""Build explicit single-message execution choices from the current filing plan."""

from copy import deepcopy

from mailAgent.executionPlan import (
    executionActionId,
    executionPlanBuild,
    executionPlanPrepare,
)


def executionReviewBuild(filingPlan: dict, config: dict) -> dict:
    """Return currently executable live-year IMAP File actions for TUI review."""
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

    result = executionPlanBuild(approved, config, current)
    evidence = _filingEvidence(filingPlan)
    candidates = []
    for action in result["actions"]:
        source = action["source"]
        original = evidence.get(_sourceKey(source), {})
        originalSource = original.get("source", {})
        candidates.append(
            dict(
                actionId=action["actionId"],
                mailbox=source["mailbox"],
                uid=source["uid"],
                year=action["year"],
                sender=originalSource.get("sender", ""),
                domain=originalSource.get("domain", ""),
                canonical=action["canonical"],
                destination=action["destination"]["folder"],
                createFolder=bool(action.get("requiresFolderCreation")),
            )
        )
    return dict(
        schemaVersion=1,
        current=current,
        approved=approved,
        candidates=candidates,
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
