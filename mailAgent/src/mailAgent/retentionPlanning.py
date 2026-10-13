"""Read-only planning for aging personal IMAP mail into local archives."""

from datetime import date
from pathlib import Path

from mailAgent.archiveDiscovery import archiveDiscover
from mailAgent.messageInventory import folderSystemKind
from mailAgent.migrationPlanning import _imapNameDecode
from mailAgent.retentionPolicy import retentionArchiveEligible, retentionCutoff


def retentionPlanBuild(
    config: dict,
    snapshot: dict,
    *,
    today: date | None = None,
    archives: list[dict] | None = None,
) -> dict:
    """Return proposed retention actions without mutating IMAP or local archives."""
    currentDate = today or date.today()
    months = config.get("general", {}).get("imapRetentionMonths", 12)
    cutoff = retentionCutoff(currentDate, months)
    observed = {mailbox.get("id"): mailbox for mailbox in snapshot.get("mailboxes", [])}
    archiveIndex = _archivesIndex(config, archives)
    plan = dict(
        schemaVersion=1,
        generatedDate=currentDate.isoformat(),
        retentionMonths=months,
        cutoffDate=cutoff.isoformat(),
        executionEnabled=False,
        proposals=[],
        blocked=[],
        mailboxes=[],
    )

    for account in config.get("mailboxes", []):
        if account.get("role") != "personal":
            continue
        mailbox = observed.get(account.get("id"))
        archive = archiveIndex.get(account.get("id"))
        beforeProposals = len(plan["proposals"])
        beforeBlocked = len(plan["blocked"])
        foldersAffected = set()

        if not isinstance(mailbox, dict) or mailbox.get("failed"):
            _blockedAppend(plan, account["id"], "Mailbox discovery unavailable")
        elif not isinstance(mailbox.get("inventory"), dict):
            _blockedAppend(plan, account["id"], "Message inventory not collected")
        elif mailbox["inventory"].get("complete") is not True:
            _blockedAppend(plan, account["id"], "Message inventory is incomplete")
        elif not _archiveUsable(archive):
            _blockedAppend(plan, account["id"], "Authoritative local archive unavailable")
        else:
            folderIndex = {
                folder.get("path"): folder
                for folder in mailbox.get("folders", [])
                if isinstance(folder, dict) and isinstance(folder.get("path"), str)
            }
            localIndex = _localIndex(archive)
            for message in mailbox["inventory"].get("messages", []):
                _messagePlan(
                    plan,
                    account,
                    mailbox,
                    archive,
                    folderIndex,
                    localIndex,
                    message,
                    cutoff,
                    months,
                    foldersAffected,
                )

        plan["mailboxes"].append(
            dict(
                mailbox=account["id"],
                archiveStore=account["id"],
                cutoffDate=cutoff.isoformat(),
                proposals=len(plan["proposals"]) - beforeProposals,
                blocked=len(plan["blocked"]) - beforeBlocked,
                foldersAffected=len(foldersAffected),
            )
        )

    plan["summary"] = dict(
        proposals=len(plan["proposals"]),
        blocked=len(plan["blocked"]),
        foldersAffected=len({
            (entry["source"]["mailbox"], entry["canonical"])
            for entry in plan["proposals"]
        }),
    )
    return plan


def _messagePlan(
    plan: dict,
    account: dict,
    mailbox: dict,
    archive: dict,
    folderIndex: dict,
    localIndex: dict,
    message: dict,
    cutoff: date,
    months: int,
    foldersAffected: set,
) -> None:
    source = _sourceBuild(account, message)
    messageDate = _messageDate(message)
    if messageDate is None:
        _blockedAppend(
            plan,
            account["id"],
            "Message date unavailable for retention",
            source=source,
        )
        return
    if not retentionArchiveEligible(messageDate, cutoff):
        return

    folder = folderIndex.get(message.get("folder"))
    if not isinstance(folder, dict):
        _blockedAppend(plan, account["id"], "Message folder not observed", source=source)
        return
    if folderSystemKind(folder) in ("trash", "junk", "drafts"):
        return

    canonical = _canonicalResolve(account, mailbox, folder)
    if not canonical:
        _blockedAppend(
            plan,
            account["id"],
            "IMAP folder has no safe canonical archive mapping",
            source=source,
        )
        return
    local = localIndex.get(canonical, [])
    if len(local) != 1 or local[0].get("selectable") is not True:
        _blockedAppend(
            plan,
            account["id"],
            "Canonical local archive destination unavailable or ambiguous",
            source=source,
            canonical=canonical,
        )
        return

    destination = local[0]
    foldersAffected.add(canonical)
    plan["proposals"].append(
        dict(
            label="Retention",
            status="proposed",
            action="archive",
            source=source,
            messageDate=messageDate.isoformat(),
            cutoffDate=cutoff.isoformat(),
            retentionMonths=months,
            canonical=canonical,
            destination=dict(
                kind="local",
                mailbox=account["id"],
                folder=canonical,
                path=destination.get("storage"),
                format=archive.get("format", "thunderbird"),
            ),
            requiresFolderCreation=False,
            requiresConfirmation=True,
            verificationRequired=True,
            sourceRemovalAllowed=False,
        )
    )


def _archivesIndex(config: dict, archives: list[dict] | None) -> dict:
    if archives is not None:
        return {
            archive.get("mailbox"): archive
            for archive in archives
            if isinstance(archive, dict) and archive.get("mailbox")
        }
    result = {}
    for account in config.get("mailboxes", []):
        if account.get("role") != "personal" or not account.get("localArchive"):
            continue
        archive = archiveDiscover(
            Path(account["localArchive"]), account.get("archiveFormat", "thunderbird")
        )
        archive["mailbox"] = account["id"]
        result[account["id"]] = archive
    return result


def _archiveUsable(archive: dict | None) -> bool:
    return bool(
        isinstance(archive, dict)
        and archive.get("available")
        and archive.get("complete", True)
    )


def _localIndex(archive: dict) -> dict:
    result = {}
    for folder in archive.get("folders", []):
        path = folder.get("path") if isinstance(folder, dict) else None
        if isinstance(path, str) and path:
            result.setdefault(path, []).append(folder)
    return result


def _canonicalResolve(account: dict, mailbox: dict, folder: dict) -> str | None:
    path = folder.get("path")
    if path in account.get("folderMappings", {}):
        return account["folderMappings"][path]
    if not isinstance(path, str) or not path:
        return None
    try:
        decoded = _imapNameDecode(path)
    except (ValueError, UnicodeError):
        return None

    namespace = mailbox.get("namespace")
    delimiter = folder.get("delimiter")
    if isinstance(namespace, dict):
        prefix = namespace.get("prefix")
        namespaceDelimiter = namespace.get("delimiter")
        if isinstance(namespaceDelimiter, str) and namespaceDelimiter:
            delimiter = namespaceDelimiter
        if isinstance(prefix, str) and prefix:
            if not decoded.startswith(prefix):
                return None
            decoded = decoded[len(prefix) :]
    if not decoded or not isinstance(delimiter, str) or not delimiter:
        return None
    parts = decoded.split(delimiter)
    if any(not part or "/" in part for part in parts):
        return None
    canonical = "/".join(parts)
    return None if canonical.upper() == "INBOX" else canonical


def _messageDate(message: dict) -> date | None:
    value = message.get("messageDate")
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _sourceBuild(account: dict, message: dict) -> dict:
    source = dict(mailbox=account["id"])
    for key in ("folder", "uidValidity", "uid"):
        if key in message:
            source[key] = message[key]
    return source


def _blockedAppend(plan: dict, mailbox: str, reason: str, **details) -> None:
    plan["blocked"].append(dict(mailbox=mailbox, reason=reason, **details))
