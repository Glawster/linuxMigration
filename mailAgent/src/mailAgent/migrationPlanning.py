"""Canonical folder mapping and role-aware proposals; execution is disabled."""

import base64
from pathlib import Path

from organiseMyProjects.logUtils import getLogger

from mailAgent.archiveDiscovery import archiveDiscover
from mailAgent.configuration import configValidate

## workflow


def migrationPlan(config: dict, snapshot: dict) -> dict:
    """Build a reviewable plan from observed folders and message metadata."""
    config = configValidate(config, Path.cwd())
    logger = getLogger()
    logger.doing("migration planning")
    plan = dict(
        schemaVersion=1,
        liveYear=config["general"]["liveYear"],
        executionEnabled=False,
        archives=[],
        mappings=[],
        proposals=[],
        reviewQueue=[],
        excluded=[],
    )
    accounts = {account["id"]: account for account in config["mailboxes"]}
    observed = {mailbox["id"]: mailbox for mailbox in snapshot["mailboxes"]}
    archives, mappings = {}, {}
    for account in accounts.values():
        if account["role"] == "personal":
            _personalDiscover(account, observed, archives, mappings, plan)
    for account in accounts.values():
        if account["role"] in ("shared", "support"):
            plan["excluded"].append(
                dict(
                    mailbox=account["id"],
                    role=account["role"],
                    reason=(
                        "Preserve shared server taxonomy"
                        if account["role"] == "shared"
                        else "Access-only; excluded from archive and migration"
                    ),
                )
            )
            continue
        _accountPlan(account, accounts, observed, archives, mappings, plan)
    logger.done("migration planning")
    return plan


## mapping


def folderMappingsBuild(account: dict, mailbox: dict, archive: dict) -> list[dict]:
    """Match canonical local folders exactly; propose missing IMAP mirrors."""
    folders = mailbox.get("folders", [])
    delimiters = {
        folder["delimiter"] for folder in folders if folder["delimiter"] is not None
    }
    delimiter = next(iter(delimiters)) if len(delimiters) == 1 else None
    return [
        _mappingBuild(account, mailbox, local, folders, delimiter)
        for local in archive["folders"]
    ]


def _mappingBuild(
    account: dict, mailbox: dict, local: dict, folders: list, delimiter: str | None
) -> dict:
    mapping = dict(
        mailbox=account["id"],
        canonical=local["path"],
        local=local["storage"],
        localSelectable=local["selectable"],
        imap=None,
        imapExists=False,
        imapSelectable=False,
        label="Inferred",
    )
    matches = [
        folder
        for folder in folders
        if _canonicalResolve(account, folder) == local["path"]
    ]
    if mailbox.get("failed") or not mailbox:
        mapping["issue"] = "Target mailbox discovery unavailable"
    elif len(matches) > 1:
        mapping["issue"] = "Multiple server folders match the canonical folder"
    elif len(matches) == 1:
        mapping.update(
            imap=matches[0]["path"],
            imapExists=True,
            imapSelectable="\\noselect"
            not in [a.lower() for a in matches[0]["attributes"]],
        )
    else:
        _mirrorPropose(local, folders, delimiter, mapping)
    return mapping


def _mirrorPropose(
    local: dict, folders: list, delimiter: str | None, mapping: dict
) -> None:
    if delimiter and not any(delimiter in part for part in local["path"].split("/")):
        proposed = _imapNameEncode(delimiter.join(local["path"].split("/")))
        if any(folder["path"] == proposed for folder in folders):
            mapping["issue"] = (
                "Proposed mirror collides with an existing folder mapping"
            )
        else:
            mapping.update(imap=proposed, mirrorProposed=True)
    else:
        mapping["issue"] = "Cannot infer a safe server delimiter for the mirror"


## planning


def _accountPlan(
    account: dict,
    accounts: dict,
    observed: dict,
    archives: dict,
    mappings: dict,
    plan: dict,
) -> None:
    mailbox = observed.get(account["id"])
    if not mailbox or mailbox.get("failed"):
        _reviewAppend(plan, account["id"], "Source mailbox discovery unavailable")
        return
    inventory = mailbox.get("inventory")
    if not inventory:
        _reviewAppend(
            plan, account["id"], "Message inventory not collected; run with --plan"
        )
        return
    for issue in inventory["issues"]:
        _reviewAppend(plan, account["id"], issue["message"], folder=issue["folder"])
    if not inventory["complete"]:
        _reviewAppend(
            plan, account["id"], "Incomplete inventory; rescan before using proposals"
        )
        return
    target = (
        accounts[account["migrationTarget"]] if account["role"] == "legacy" else account
    )
    archive = archives[target["id"]]
    sourceFolders = {folder["path"]: folder for folder in mailbox["folders"]}
    for message in inventory["messages"]:
        _messagePlan(
            account,
            target,
            message,
            sourceFolders,
            archive,
            mappings[target["id"]],
            plan,
        )


def _destinationBuild(
    source: dict, target: dict, year: int, liveYear: int, mapping: dict, archive: dict
) -> tuple[dict, str]:
    if year < liveYear:
        if not mapping["localSelectable"]:
            raise ValueError("Canonical folder has no local message store")
        return (
            dict(
                kind="local",
                mailbox=target["id"],
                folder=mapping["canonical"],
                path=mapping["local"],
                format=archive["format"],
            ),
            "archive",
        )
    if (
        mapping.get("issue")
        or not mapping["imap"]
        or (mapping["imapExists"] and not mapping["imapSelectable"])
    ):
        raise ValueError(mapping.get("issue", "IMAP target cannot receive messages"))
    destination = dict(
        kind="imap",
        mailbox=target["id"],
        folder=mapping["imap"],
        exists=mapping["imapExists"],
    )
    action = (
        "retain"
        if source["mailbox"] == target["id"] and source["folder"] == mapping["imap"]
        else "migrate"
    )
    return destination, action


def _messageMapping(
    account: dict,
    message: dict,
    sourceFolders: dict,
    archive: dict,
    mappings: list,
    liveYear: int,
) -> dict:
    year = message.get("year")
    if type(year) is not int or year > liveYear or year < 1900:
        raise ValueError(message.get("issue", "Unknown or future message year"))
    folder = sourceFolders.get(message["folder"])
    if not folder:
        raise ValueError("Message folder not observed")
    if any(
        attribute.lower() in ("\\trash", "\\junk", "\\drafts")
        for attribute in folder["attributes"]
    ):
        raise ValueError("System folder requires a separate retention decision")
    canonical = _canonicalResolve(account, folder)
    candidates = [mapping for mapping in mappings if mapping["canonical"] == canonical]
    if (
        len(candidates) != 1
        or not archive["available"]
        or not archive.get("complete", True)
    ):
        raise ValueError("No unambiguous canonical archive folder")
    return candidates[0]


def _messagePlan(
    account: dict,
    target: dict,
    message: dict,
    sourceFolders: dict,
    archive: dict,
    mappings: list,
    plan: dict,
) -> None:
    source = {
        "mailbox": account["id"],
        **{key: message[key] for key in ("folder", "uid", "uidValidity")},
    }
    try:
        mapping = _messageMapping(
            account, message, sourceFolders, archive, mappings, plan["liveYear"]
        )
        destination, action = _destinationBuild(
            source, target, message["year"], plan["liveYear"], mapping, archive
        )
    except ValueError as error:
        _reviewAppend(plan, account["id"], str(error), source=source)
        return
    plan["proposals"].append(
        dict(
            label="Inferred",
            status="proposed",
            action=action,
            source=source,
            year=message["year"],
            dateBasis="Date header",
            canonical=mapping["canonical"],
            destination=destination,
            requiresFolderCreation=destination.get("exists") is False,
            requiresConfirmation=action != "retain",
            verificationRequired=action != "retain",
            sourceRemovalAllowed=False,
        )
    )


def _personalDiscover(
    account: dict, observed: dict, archives: dict, mappings: dict, plan: dict
) -> None:
    archive = archiveDiscover(
        Path(account["localArchive"]),
        account.get("archiveFormat", "thunderbird"),
    )
    archive["mailbox"] = account["id"]
    archives[account["id"]] = archive
    plan["archives"].append(archive)
    mailbox = observed.get(account["id"], {})
    mappings[account["id"]] = folderMappingsBuild(account, mailbox, archive)
    plan["mappings"].extend(mappings[account["id"]])
    for issue in archive["issues"]:
        _reviewAppend(plan, account["id"], issue)
    for mapping in mappings[account["id"]]:
        if mapping.get("issue"):
            _reviewAppend(
                plan,
                account["id"],
                mapping["issue"],
                folder=mapping["canonical"],
            )


## utilities


def _canonicalResolve(account: dict, folder: dict) -> str | None:
    if folder["path"] in account.get("folderMappings", {}):
        return account["folderMappings"][folder["path"]]
    try:
        path = _imapNameDecode(folder["path"])
    except (ValueError, UnicodeError):
        return None
    delimiter = folder["delimiter"]
    parts = path.split(delimiter) if delimiter else [path]
    if any(not part or "/" in part and delimiter != "/" for part in parts):
        return None
    return "/".join(parts)


def _imapNameDecode(value: str) -> str:
    result = []
    while "&" in value:
        prefix, value = value.split("&", 1)
        encoded, separator, value = value.partition("-")
        if not separator:
            raise ValueError("Malformed modified UTF-7")
        result.append(prefix)
        result.append(
            base64.b64decode(
                encoded.replace(",", "/") + "=" * (-len(encoded) % 4), validate=True
            ).decode("utf-16-be")
            if encoded
            else "&"
        )
    return "".join(result) + value


def _imapNameEncode(value: str) -> str:
    result, pending = [], []
    for char in value + "\0":
        if " " <= char <= "~" or char == "\0":
            if pending:
                result.append(
                    "&"
                    + base64.b64encode("".join(pending).encode("utf-16-be"))
                    .decode()
                    .rstrip("=")
                    .replace("/", ",")
                    + "-"
                )
                pending = []
            if char != "\0":
                result.append("&-" if char == "&" else char)
        else:
            pending.append(char)
    return "".join(result)


def _reviewAppend(plan: dict, mailbox: str, reason: str, **details) -> None:
    plan["reviewQueue"].append(
        dict(label="Warning/Conflict", mailbox=mailbox, reason=reason, **details)
    )
