"""Discovery orchestration, reconciliation and secret-free persistence."""

import imaplib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit

from organiseMyProjects.logUtils import getLogger

from mailAgent.credentials import CredentialError, credentialGet, credentialsLoad
from mailAgent.imapDiscovery import mailboxDiscover
from mailAgent.thunderbird import sourcesDiscover

## workflow


def discoveryRun(
    accounts: list[dict],
    thunderbirdRoot: Path,
    clientFactory=imaplib.IMAP4_SSL,
    includeMessages: bool = False,
    includeInbox: bool = False,
    credentialsFile: Path | None = None,
) -> dict:
    """Audit configured accounts independently with TLS authentication."""
    logger = getLogger()
    logger.doing("mailbox discovery")
    snapshot = dict(
        schemaVersion=1,
        timestamp=datetime.now(timezone.utc).isoformat(),
        mailboxes=[],
        sources=sourcesDiscover(thunderbirdRoot),
        issues=[],
    )
    credentials = {}
    credentialIssue = None
    try:
        if any("credentialId" in account for account in accounts):
            try:
                credentials = credentialsLoad(credentialsFile)
            except CredentialError as error:
                credentialIssue = str(error)
        for account in accounts:
            snapshot["mailboxes"].append(
                _accountDiscover(
                    account,
                    clientFactory,
                    includeMessages,
                    includeInbox,
                    credentials,
                    credentialIssue,
                    logger,
                )
            )
    finally:
        credentials.clear()
    snapshot["relationships"], snapshot["conflicts"] = filtersReconcile(snapshot)
    logger.done("mailbox discovery")
    return snapshot


## failures


def _accountDiscover(
    account: dict,
    clientFactory,
    includeMessages: bool,
    includeInbox: bool,
    credentials: dict,
    credentialIssue: str | None,
    logger,
) -> dict:
    client = None
    try:
        if "credentialId" in account and credentialIssue is not None:
            raise CredentialError(credentialIssue)
        password = credentialGet(account, credentials=credentials)
        try:
            client = clientFactory(
                account["host"], account.get("port", 993), timeout=30
            )
            client.login(account["username"], password)
        finally:
            del password
        mailbox = mailboxDiscover(client, account)
        mailbox["role"] = account.get("role", "unspecified")
        if includeMessages and account.get("role") in ("personal", "legacy"):
            from mailAgent.messageInventory import messagesDiscover

            mailbox["inventory"] = messagesDiscover(client, mailbox["folders"])
        elif includeInbox:
            from mailAgent.messageInventory import inboxMessagesDiscover

            mailbox["inboxInventory"] = inboxMessagesDiscover(
                client, mailbox["folders"]
            )
        return mailbox
    except CredentialError as error:
        return _mailboxFailed(account, str(error))
    except Exception:
        return _mailboxFailed(
            account, "Mailbox discovery failed; verify connection and credentials"
        )
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                logger.warning("imap logout failed")


def _mailboxFailed(account: dict, issue: str) -> dict:
    return {
        **{key: account[key] for key in ("id", "name", "host", "username")},
        "folders": [],
        "quota": [],
        "issues": [issue],
        "failed": True,
        "role": account.get("role", "unspecified"),
    }


## reconciliation


def filtersReconcile(snapshot: dict) -> tuple[list, list]:
    """Resolve exact URI account/path identities and label advisory overlaps."""
    relationships, conflicts = [], []
    for source in snapshot["sources"]:
        source["mailboxIds"] = [
            mailbox["id"]
            for mailbox in snapshot["mailboxes"]
            if any(
                identity["host"] == mailbox["host"]
                and identity["username"] == mailbox["username"]
                for identity in source.get("identities", [])
            )
        ]
        for index, rule in enumerate(source["filters"]):
            identity = f'{source["path"]}#{index}'
            text = " ".join(
                [rule["name"], *rule["conditions"], *rule["destinations"]]
            ).lower()
            categories = [
                category
                for category, words in {
                    "Active Order": ("order", "purchase"),
                    "Active Delivery": ("delivery", "tracking", "shipment"),
                    "Completed Order": ("completed",),
                    "For Me": ("personal", "important"),
                    "General": ("general", "misc"),
                }.items()
                if any(word in text for word in words)
            ]
            if categories:
                conflicts.append(
                    dict(
                        label="Inferred",
                        filter=identity,
                        categories=categories,
                        message="Likely overlap with classification categories; review only",
                    )
                )
            for issue in rule["issues"]:
                conflicts.append(
                    dict(label="Warning/Conflict", filter=identity, message=issue)
                )
            for target in rule["destinations"]:
                try:
                    uri = urlsplit(target)
                    candidates = [
                        dict(mailbox=mailbox["id"], folder=folder["path"])
                        for mailbox in snapshot["mailboxes"]
                        for folder in mailbox["folders"]
                        if uri.scheme == "imap"
                        and uri.hostname == mailbox["host"].lower()
                        and unquote(uri.username or "") == mailbox["username"]
                        and unquote(uri.path.lstrip("/")) == folder["path"]
                    ]
                except ValueError:
                    candidates = []
                resolved = len(candidates) == 1
                relationships.append(
                    dict(
                        filter=identity,
                        target=target,
                        resolved=resolved,
                        candidates=candidates,
                        label="Observed" if resolved else "Warning/Conflict",
                    )
                )
                if not resolved:
                    conflicts.append(
                        dict(
                            label="Warning/Conflict",
                            filter=identity,
                            message="Unresolved or ambiguous destination",
                            target=target,
                        )
                    )
    targets = {}
    for link in relationships:
        targets.setdefault(link["target"], set()).add(link["filter"])
    for target, filters in targets.items():
        if len(filters) > 1:
            conflicts.append(
                dict(
                    label="Warning/Conflict",
                    target=target,
                    filters=sorted(filters),
                    message="Multiple filters share a destination",
                )
            )
    return relationships, conflicts


## snapshots


def snapshotCompare(previous: dict, current: dict) -> list[dict]:
    """Compare structural changes without treating failed scans as removals."""
    changes = []
    oldFolders = {
        (m["id"], f["path"])
        for m in previous.get("mailboxes", [])
        for f in m["folders"]
    }
    newFolders = {
        (m["id"], f["path"]) for m in current["mailboxes"] for f in m["folders"]
    }
    failed = {m["id"] for m in current["mailboxes"] if m.get("failed")}
    for kind, items in (
        ("folder added", newFolders - oldFolders),
        ("folder removed", oldFolders - newFolders),
    ):
        changes.extend(
            dict(kind=kind, identity=item)
            for item in sorted(items)
            if item[0] not in failed
        )
    oldRules, newRules = _rulesIndex(previous), _rulesIndex(current)
    for kind, keys in (
        ("filter added", newRules.keys() - oldRules.keys()),
        ("filter removed", oldRules.keys() - newRules.keys()),
    ):
        changes.extend(dict(kind=kind, identity=key) for key in sorted(keys))
    for key in sorted(oldRules.keys() & newRules.keys()):
        for field in ("enabled", "destinations"):
            if oldRules[key][field] != newRules[key][field]:
                changes.append(
                    dict(
                        kind="filter " + field + " changed",
                        identity=key,
                        before=oldRules[key][field],
                        after=newRules[key][field],
                    )
                )
    return changes


def snapshotSave(snapshot: dict, root: Path) -> Path:
    """Atomically publish latest after writing a unique historical snapshot."""
    previous = (
        json.loads((root / "latest.json").read_text())
        if (root / "latest.json").is_file()
        else {}
    )
    if previous and previous.get("schemaVersion") != 1:
        raise ValueError("Unsupported previous snapshot schema")
    snapshot["changes"] = snapshotCompare(previous, snapshot)
    history = root / "history"
    history.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot, indent=2, ensure_ascii=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    path = history / f"discovery-{stamp}.json"
    path.write_text(payload)
    with tempfile.NamedTemporaryFile(mode="w", dir=root, delete=False) as temporary:
        temporary.write(payload)
    os.replace(temporary.name, root / "latest.json")
    return path


def _rulesIndex(snapshot: dict) -> dict:
    result = {}
    for source in snapshot.get("sources", []):
        occurrences = {}
        for rule in source["filters"]:
            name = rule["name"]
            occurrences[name] = occurrences.get(name, 0) + 1
            result[(source["path"], name, occurrences[name])] = rule
    return result
