"""Pure approval-boundary validation; no network, archive writes or UI imports."""

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

_SCHEMA = 1
_ACCOUNT_FIELDS = (
    "id",
    "host",
    "port",
    "username",
    "role",
    "localArchive",
    "archiveFormat",
    "folderMappings",
    "migrationTarget",
    "junkKeyword",
)

## execution


def executionActionId(action: dict) -> str:
    """Hash immutable action identity, including destination and creation approval."""
    return sha256(_encoded(_actionIdentity(action))).hexdigest()


def executionActionValidate(action: dict) -> dict:
    """Return a sanitized approved action; does not establish fresh eligibility."""
    _fingerprintValidate(action.get("configFingerprint"))
    rebuilt = _actionBuild(action, action["configFingerprint"])
    if rebuilt["disposition"] == "file" and rebuilt["destination"]["kind"] == "local":
        path = rebuilt["destination"]["path"]
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise ValueError("Local execution requires an explicit absolute path")
    if (
        action.get("approved") is not True
        or action.get("executionPermitted") is not True
        or action.get("actionId") != rebuilt["actionId"]
    ):
        raise ValueError("Invalid approved execution action")
    rebuilt.update(approved=True, executionPermitted=True)
    return rebuilt


def executionConfigFingerprint(config: dict) -> str:
    """Bind approval to connection identities and policy, excluding credentials."""
    accounts = config.get("mailboxes")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("Invalid execution configuration")
    projected = []
    identifiers = set()
    for account in accounts:
        for key in ("id", "host", "username", "role"):
            _text(account.get(key))
        if account["id"] in identifiers:
            raise ValueError("Duplicate mailbox identity")
        identifiers.add(account["id"])
        projected.append({key: account.get(key) for key in _ACCOUNT_FIELDS})
    return sha256(
        _encoded(
            dict(
                liveYear=config.get("general", {}).get("liveYear"),
                mailboxes=sorted(projected, key=lambda entry: entry["id"]),
            )
        )
    ).hexdigest()


def executionPlanBuild(
    approved: dict,
    config: dict,
    current: dict,
    completedActionIds: set[str] | None = None,
) -> dict:
    """Validate approved actions against a fresh envelope, blocking stale entries.

    Current must be rebuilt from fresh read-only discovery using executionPlanPrepare.
    The result authorizes no mutation: a future engine must probe again immediately
    before acting. Completed IDs are supplied by the journal.
    """
    _envelopeValidate(approved)
    _envelopeValidate(current)
    fingerprint = executionConfigFingerprint(config)
    if (
        approved["configFingerprint"] != fingerprint
        or current["configFingerprint"] != fingerprint
    ):
        raise ValueError("Configuration or mailbox identity changed")
    completed = completedActionIds or set()
    result = dict(
        schemaVersion=_SCHEMA,
        executionEnabled=False,
        actions=[],
        blocked=[],
        completed=[],
    )
    accounts = {entry["id"]: entry for entry in config["mailboxes"]}
    currentIndex = _currentIndex(current)
    sources = Counter()
    for entry in approved["entries"]:
        try:
            sources[_sourceKey(_actionBuild(entry, fingerprint)["source"])] += 1
        except (ValueError, KeyError, TypeError):
            pass
    for index, entry in enumerate(approved["entries"]):
        action = None
        try:
            action = _actionBuild(entry, fingerprint)
            sourceKey = _sourceKey(action["source"])
            if sources[sourceKey] != 1:
                raise ValueError("Duplicate or conflicting source action")
            _approvalValidate(approved, entry, action)
            action.update(approved=True, executionPermitted=True)
            _scopeValidate(action, accounts, config["general"]["liveYear"])
            if action["actionId"] in completed:
                result["completed"].append(action["actionId"])
                continue
            _currentValidate(action, currentIndex)
            result["actions"].append(action)
        except (ValueError, KeyError, TypeError) as error:
            # Store fixed reasons and an index, never untrusted entries or bodies.
            blocked = dict(index=index, reason=str(error))
            if action is not None and action.get("approved") is True:
                blocked["action"] = action
            result["blocked"].append(blocked)
    return result


def executionPlanPrepare(filingPlan: dict, config: dict) -> dict:
    """Wrap read-only filing entries for later approval; grant no permissions."""
    if (
        type(filingPlan.get("schemaVersion")) is not int
        or filingPlan["schemaVersion"] != _SCHEMA
    ):
        raise ValueError("Unsupported filing plan schema")
    fingerprint = executionConfigFingerprint(config)
    entries = []
    for entry in filingPlan.get("proposals", []) + filingPlan.get("dispositions", []):
        action = _actionBuild(entry, fingerprint)
        action.pop("actionId")
        action.pop("configFingerprint")
        action.update(
            approved=False, executionPermitted=False, folderCreationApproved=False
        )
        entries.append(action)
    return dict(
        schemaVersion=_SCHEMA,
        configFingerprint=fingerprint,
        executionEnabled=False,
        entries=entries,
    )


## validation


def _actionBuild(entry: dict, fingerprint: str) -> dict:
    source = entry["source"]
    identity = {key: source[key] for key in ("mailbox", "folder", "uidValidity", "uid")}
    for key in ("mailbox", "folder"):
        _text(identity[key])
    for key in ("uidValidity", "uid"):
        value = identity[key]
        if (
            not isinstance(value, str)
            or not value.isascii()
            or not value.isdigit()
            or not 0 < int(value) <= 4294967295
        ):
            raise ValueError("Invalid source UID identity")
        identity[key] = str(int(value))
    if (
        identity["folder"].upper() != "INBOX"
        or source.get("seen") is not True
        or entry.get("readState") != "read"
    ):
        raise ValueError("Source is not a read Inbox message")
    identity["seen"] = True
    disposition = entry.get("disposition")
    if disposition not in ("file", "ignore", "junk"):
        raise ValueError("Unsupported disposition")
    if entry.get("decisionSource") not in ("sender", "domain", "archive history"):
        raise ValueError("Unsupported decision source")
    year = entry.get("year")
    if year is not None and (type(year) is not int or not 1900 <= year <= 9999):
        raise ValueError("Invalid eligibility year")
    action = dict(
        source=identity,
        disposition=disposition,
        readState="read",
        year=entry.get("year"),
        decisionSource=entry["decisionSource"],
        configFingerprint=fingerprint,
        folderCreationApproved=entry.get("folderCreationApproved", False),
    )
    if type(action["folderCreationApproved"]) is not bool:
        raise ValueError("Invalid folder approval")
    if disposition == "file":
        _canonicalValidate(entry.get("canonical"))
        destination = entry["destination"]
        kind = destination.get("kind")
        if kind not in ("imap", "local"):
            raise ValueError("Unsupported destination kind")
        keys = (
            ("kind", "mailbox", "folder")
            if kind == "imap"
            else ("kind", "mailbox", "folder", "path", "format")
        )
        action["destination"] = {key: destination[key] for key in keys}
        if kind == "local" and (
            destination["format"] != "thunderbird"
            or (
                destination["path"] is not None
                and not isinstance(destination["path"], str)
            )
        ):
            raise ValueError("Invalid local archive identity")
        for key in ("mailbox", "folder"):
            _text(destination[key])
        action["canonical"] = entry["canonical"]
        create = entry.get("requiresFolderCreation")
        if type(create) is not bool:
            raise ValueError("Invalid folder creation requirement")
        action["requiresFolderCreation"] = create
    elif (
        any(key in entry for key in ("canonical", "destination"))
        or action["folderCreationApproved"]
    ):
        raise ValueError("Non-file action contains a destination")
    action["actionId"] = executionActionId(action)
    return action


def _actionIdentity(action: dict) -> dict:
    keys = (
        "source",
        "disposition",
        "year",
        "decisionSource",
        "configFingerprint",
        "folderCreationApproved",
    )
    result = {key: action[key] for key in keys}
    if action["disposition"] == "file":
        result.update(destination=action["destination"], canonical=action["canonical"])
    return result


def _approvalValidate(plan: dict, entry: dict, action: dict) -> None:
    if (
        plan["executionEnabled"] is not True
        or entry.get("approved") is not True
        or entry.get("executionPermitted") is not True
    ):
        raise ValueError("Action is not explicitly approved for execution")
    if entry.get("actionId") != action["actionId"]:
        raise ValueError("Approval identity does not match action")
    if action.get("requiresFolderCreation") and not action["folderCreationApproved"]:
        raise ValueError("Folder creation was not approved")


def _canonicalValidate(value: str) -> None:
    _text(value)
    if any(part in ("", ".", "..") or "\\" in part for part in value.split("/")):
        raise ValueError("Unsafe canonical destination")


def _currentIndex(current: dict) -> dict:
    indexed = {}
    for entry in current["entries"]:
        try:
            candidate = _actionBuild(entry, current["configFingerprint"])
        except (ValueError, KeyError, TypeError):
            continue
        indexed.setdefault(_sourceKey(candidate["source"]), []).append(candidate)
    return indexed


def _currentValidate(action: dict, currentIndex: dict) -> None:
    matches = currentIndex.get(_sourceKey(action["source"]), [])
    if len(matches) != 1:
        raise ValueError("Source missing, stale UIDVALIDITY, ineligible or ambiguous")
    candidate = dict(matches[0])
    # Creation permission belongs to approval; existence may change idempotently.
    candidate["folderCreationApproved"] = action["folderCreationApproved"]
    if _actionIdentity(candidate) != _actionIdentity(action):
        raise ValueError(
            "Disposition, destination or eligibility changed since approval"
        )
    if candidate.get("requiresFolderCreation") and not action["folderCreationApproved"]:
        raise ValueError("Destination disappeared without creation approval")


def _envelopeValidate(plan: dict) -> None:
    if (
        not isinstance(plan, dict)
        or type(plan.get("schemaVersion")) is not int
        or plan["schemaVersion"] != _SCHEMA
    ):
        raise ValueError("Unsupported execution plan schema")
    if type(plan.get("executionEnabled")) is not bool or not isinstance(
        plan.get("entries"), list
    ):
        raise ValueError("Invalid execution plan envelope")
    _fingerprintValidate(plan.get("configFingerprint"))


def _fingerprintValidate(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError("Invalid configuration fingerprint")


def _scopeValidate(action: dict, accounts: dict, liveYear: int) -> None:
    source = accounts.get(action["source"]["mailbox"])
    if not source or source["role"] != "personal":
        raise ValueError("Execution is limited to personal mailboxes")
    if action["disposition"] != "file":
        if action["disposition"] == "junk" and not source.get("junkKeyword"):
            raise ValueError("Account junk mechanism is not configured")
        if action["disposition"] == "junk":
            keyword = source["junkKeyword"]
            _text(keyword)
            if any(char.isspace() or char in '(){%*"\\]' for char in keyword):
                raise ValueError("Invalid account junk keyword")
        return
    destination = action["destination"]
    if destination["mailbox"] != source["id"]:
        raise ValueError("Cross-mailbox execution is not supported")
    year = action["year"]
    if type(year) is not int or not 1900 <= year <= liveYear:
        raise ValueError("Invalid filing year")
    if destination["kind"] == "imap":
        if year != liveYear or destination["folder"].upper() == "INBOX":
            raise ValueError("Invalid live-year destination")
    else:
        if (
            year >= liveYear
            or destination["format"] != "thunderbird"
            or destination["folder"] != action["canonical"]
        ):
            raise ValueError("Invalid Thunderbird archive destination")
        root = Path(source["localArchive"]).resolve()
        path = destination["path"]
        if not isinstance(path, str) or not Path(path).is_absolute():
            raise ValueError("Local destination must have an explicit absolute path")
        resolved = Path(path).resolve()
        if resolved == root or not resolved.is_relative_to(root):
            raise ValueError("Local destination escapes configured archive")


def _sourceKey(source: dict) -> tuple:
    return tuple(source[key] for key in ("mailbox", "folder", "uidValidity", "uid"))


def _text(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("Invalid identity text")


def _encoded(value: dict) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
