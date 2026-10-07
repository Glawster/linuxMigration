"""Read Inbox filing policy, durable rules and read-only proposals.

Phase 1 records decisions and plans destinations. It does not create folders,
move mail, or enable the later execution phase.
"""

import json
import os
import tempfile
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from organiseMyProjects.logUtils import getLogger
from publicsuffixlist import PublicSuffixList

from mailAgent.archiveClassification import archiveSenderIndex, senderClassify
from mailAgent.senderAddress import senderNormalize

_SCHEMA_VERSION = 1
_SAFE_HISTORY = ("archiveSenderExact", "archiveSenderMajority")
_CHILD_DISPLAY = {"paypal": "PayPal"}
_SECRET_KEYS = {"password", "secret", "token", "body", "subject"}
_PSL = PublicSuffixList(accept_unknown=False)
_PSL_ICANN = PublicSuffixList(accept_unknown=False, only_icann=True)


## workflow


def filingContextBuild(config: dict) -> dict:
    """Capture role and archive identity needed to rebuild a filing plan."""
    accounts = []
    for account in config["mailboxes"]:
        entry = dict(
            id=account["id"],
            role=account["role"],
            archiveFormat=account.get("archiveFormat", "thunderbird"),
            folderMappings=dict(account.get("folderMappings", {})),
        )
        if account.get("migrationTarget"):
            entry["migrationTarget"] = account["migrationTarget"]
        if account.get("localArchive"):
            entry["localArchive"] = account["localArchive"]
            entry["archiveName"] = _archiveLabel(Path(account["localArchive"]).name)
        accounts.append(entry)
    return dict(liveYear=config["general"]["liveYear"], accounts=accounts)


def filingPlanBuild(context: dict, snapshot: dict, rules: dict | None = None) -> dict:
    """Plan read Inbox filing without mutating mail or creating folders."""
    logger = getLogger()
    logger.doing("inbox filing plan")
    if rules is None:
        rules = _emptyRules()
    _rulesValidate(rules)
    _contextCheck(context)
    plan = _planEmpty(context, snapshot)
    prepared = _archivesPrepare(context, snapshot, plan)
    prepared["snapshot"] = snapshot
    prepared["history"] = {}
    _proposedCollect(plan, rules)
    grouped: dict = {}
    for account in context["accounts"]:
        _accountFile(account, snapshot, rules, prepared, plan, grouped)
    _rowsBuild(grouped, rules, prepared, plan)
    _overridesCollect(plan, rules)
    plan["proposals"].sort(key=_proposalSort)
    plan["reviews"].sort(key=_reviewSort)
    plan["rows"].sort(key=lambda row: (row["archive"].casefold(), row["domain"]))
    logger.done("inbox filing plan")
    return plan


def filingStatus(decision: dict | None, parents: list[str], folders: list[dict]) -> str:
    """Describe whether a destination already exists in the local archive."""
    if not decision or not decision.get("canonical"):
        return "Needs choice"
    parent = decision.get("parent", "")
    canonical = decision["canonical"]
    parentExists = parent in parents
    folderExists = any(
        folder.get("path") == canonical and folder.get("selectable")
        for folder in folders
    )
    if parentExists and folderExists:
        return "Existing"
    if parentExists:
        return "Proposed child"
    return "Proposed parent + child"


## rules


def filingDomainClarify(
    mailbox: str, host: str, domain: str, path: Path | None = None
) -> dict:
    """Record the organisation domain chosen for one uncertain sender host."""
    _mailboxCheck(mailbox)
    observed = _hostKey(host)
    if filingDomainExtract("sender@" + observed):
        raise ValueError("Domain does not need clarification")
    chosen = _domainKey(domain)
    path = path or filingPath()
    data = filingRulesLoad(path)
    entry = _mailboxEntry(data, mailbox)
    entry["clarifications"][observed] = chosen
    return _filingWrite(data, path)


def filingDomainSet(
    mailbox: str,
    domain: str,
    parent: str,
    child: str,
    parentProposed: bool,
    path: Path | None = None,
) -> dict:
    """Persist one mailbox-specific domain filing rule."""
    _mailboxCheck(mailbox)
    domain = _domainKey(domain)
    decision = _decisionBuild(parent, child, parentProposed)
    return _decisionStore(mailbox, "domains", domain, decision, path)


def filingParentAdd(mailbox: str, parent: str, path: Path | None = None) -> dict:
    """Record a proposed parent. This does not create an archive folder."""
    _mailboxCheck(mailbox)
    parent = filingNameNormalize(parent)
    path = path or filingPath()
    data = filingRulesLoad(path)
    entry = _mailboxEntry(data, mailbox)
    if parent not in entry["proposedParents"]:
        entry["proposedParents"].append(parent)
    entry["proposedParents"].sort(key=str.casefold)
    return _filingWrite(data, path)


def filingPath() -> Path:
    """Return the durable filing-rules path."""
    return Path.home() / ".config/mailAgent/filing-rules.json"


def filingRulesLoad(path: Path | None = None) -> dict:
    """Load filing rules. A missing file is an empty rule set."""
    path = path or filingPath()
    if not path.exists():
        return _emptyRules()
    data = json.loads(path.read_text())
    _rulesValidate(data)
    return data


def filingSenderSet(
    mailbox: str,
    sender: str,
    parent: str,
    child: str,
    parentProposed: bool,
    path: Path | None = None,
) -> dict:
    """Persist an exact sender override for one mailbox taxonomy."""
    _mailboxCheck(mailbox)
    normalized = senderNormalize(sender)
    if not normalized or not _senderHost(normalized):
        raise ValueError("Invalid filing sender")
    decision = _decisionBuild(parent, child, parentProposed)
    return _decisionStore(mailbox, "senders", normalized, decision, path)


## naming


def filingChildSuggest(domain: str, folders: list | None = None) -> str:
    """Suggest a readable child folder from the organisation label."""
    label = domain.split(".", 1)[0]
    spelling = _existingSpelling(label, folders or [])
    if spelling:
        return spelling
    if label.casefold() in _CHILD_DISPLAY:
        return _CHILD_DISPLAY[label.casefold()]
    if label.isalpha() and len(label) <= 3:
        return label.upper()
    return label[:1].upper() + label[1:]


def filingDomainExtract(value: str | None) -> str | None:
    """Return the organisation domain when the Public Suffix List agrees.

    The bundled list supplies the suffix boundary. A result is used only when
    the full list and its ICANN section name the same registrable domain, so
    ``amazon.co.uk`` stays intact. A public-suffix host, an unknown suffix, or
    a private-section boundary such as ``shop.blogspot.com`` returns None.
    """
    host = _senderHost(value)
    if not host:
        return None
    registrable = _PSL.privatesuffix(host)
    if not isinstance(registrable, str) or not _domainLabelsOk(registrable):
        return None
    if registrable != _PSL_ICANN.privatesuffix(host):
        return None
    return registrable


def filingDomainMatch(sender: str, domain: str, rules: dict, mailbox: str) -> bool:
    """Return whether one sender belongs to a filing row's domain."""
    resolved, _uncertain = _organisationDomain(sender, rules, mailbox)
    return resolved == domain


def filingNameNormalize(value: str) -> str:
    """Return one archive path component, preserving capitalisation."""
    if not isinstance(value, str):
        raise ValueError("Folder name must be text")
    name = " ".join(value.split())
    if (
        not name
        or name in (".", "..")
        or name.startswith(".")
        or name.lower().endswith(".sbd")
        or any(ord(char) < 32 or char in "/\\" for char in name)
    ):
        raise ValueError("Invalid archive folder name")
    return name


def filingParentsDiscover(archive: dict) -> list[str]:
    """Return first-level archive folders, preserving their spelling."""
    if not archive or not archive.get("available") or not archive.get("complete", True):
        return []
    found = []
    for folder in archive.get("folders", []):
        path = folder.get("path")
        if not isinstance(path, str) or not path:
            continue
        parent = path.split("/", 1)[0]
        if parent and parent not in found:
            found.append(parent)
    return sorted(found, key=str.casefold)


## utilities


def _accountFile(
    account: dict,
    snapshot: dict,
    rules: dict,
    prepared: dict,
    plan: dict,
    grouped: dict,
) -> None:
    role = account.get("role")
    if role in ("shared", "support"):
        plan["excluded"].append(
            dict(
                mailbox=account["id"],
                role=role,
                reason=(
                    "Shared mailboxes are excluded from personal Inbox filing"
                    if role == "shared"
                    else "Support mailboxes are excluded from personal Inbox filing"
                ),
            )
        )
        return
    found = _ownerAccount(account, prepared["accounts"])
    if found is None:
        _reviewAppend(
            plan,
            account["id"],
            "",
            "Personal filing taxonomy is unavailable",
        )
        return
    # Copy so the caller's configuration is not given a live-year field.
    owner = dict(found)
    owner["liveYear"] = plan["liveYear"]
    observed = _observed(snapshot, account["id"])
    inventory = observed.get("inboxInventory")
    if not isinstance(inventory, dict):
        return
    if not inventory.get("complete", True):
        _reviewAppend(
            plan,
            account["id"],
            "INBOX",
            "Inbox inventory incomplete; filing proposals withheld",
        )
        return
    archive = prepared["archives"][owner["id"]]
    for message in inventory.get("messages", []):
        _messageFile(account, owner, message, archive, rules, prepared, plan, grouped)


def _archivesPrepare(context: dict, snapshot: dict, plan: dict) -> dict:
    accounts = {account["id"]: account for account in context["accounts"]}
    archives = {}
    for account in context["accounts"]:
        if account.get("role") != "personal":
            continue
        archive = _archiveFor(snapshot, account)
        archives[account["id"]] = archive
        plan["parents"][account["id"]] = filingParentsDiscover(archive)
        plan["proposedParents"].setdefault(account["id"], [])
    return dict(accounts=accounts, archives=archives, context=context)


def _archiveFor(snapshot: dict, account: dict) -> dict:
    for archive in snapshot.get("localArchives", []):
        if archive.get("mailbox") == account["id"]:
            return archive
    root = account.get("localArchive")
    if not root:
        return dict(available=False, complete=False, folders=[], format="thunderbird")
    from mailAgent.archiveDiscovery import archiveDiscover

    archive = archiveDiscover(Path(root), account.get("archiveFormat", "thunderbird"))
    archive["mailbox"] = account["id"]
    archive["name"] = Path(root).name
    return archive


def _archiveLabel(name: str) -> str:
    return (
        name[:-4] if isinstance(name, str) and name.lower().endswith(".sbd") else name
    )


def _archiveUsable(archive: dict) -> bool:
    return bool(archive.get("available") and archive.get("complete", True))


def _contextCheck(context: dict) -> None:
    if (
        not isinstance(context, dict)
        or type(context.get("liveYear")) is not int
        or not isinstance(context.get("accounts"), list)
    ):
        raise ValueError("Invalid filing context")


def _decisionBuild(parent: str, child: str, parentProposed: bool) -> dict:
    parent = filingNameNormalize(parent)
    child = filingNameNormalize(child)
    if type(parentProposed) is not bool:
        raise ValueError("Invalid proposed-parent flag")
    return dict(
        parent=parent,
        child=child,
        canonical=f"{parent}/{child}",
        parentProposed=parentProposed,
    )


def _decisionStore(
    mailbox: str, kind: str, key: str, decision: dict, path: Path | None
) -> dict:
    path = path or filingPath()
    data = filingRulesLoad(path)
    entry = _mailboxEntry(data, mailbox)
    entry[kind][key] = decision
    if (
        decision["parentProposed"]
        and decision["parent"] not in entry["proposedParents"]
    ):
        entry["proposedParents"].append(decision["parent"])
        entry["proposedParents"].sort(key=str.casefold)
    return _filingWrite(data, path)


def _decisionValidate(decision: dict) -> None:
    if (
        not isinstance(decision, dict)
        or type(decision.get("parentProposed")) is not bool
    ):
        raise ValueError("Invalid filing decision")
    parent = decision.get("parent")
    child = decision.get("child")
    if parent != filingNameNormalize(parent) or child != filingNameNormalize(child):
        raise ValueError("Invalid filing folder name")
    if decision.get("canonical") != f"{parent}/{child}":
        raise ValueError("Filing canonical path must be parent/child")


def _destinationBuild(
    decision: dict,
    message: dict,
    owner: dict,
    observedTarget: dict,
    archive: dict,
    mappings: list,
) -> tuple[dict, bool]:
    if not _archiveUsable(archive):
        raise ValueError("Archive scan incomplete; filing destination not safe")
    year = message.get("year")
    liveYear = owner.get("liveYear")
    if (
        type(year) is not int
        or type(liveYear) is not int
        or not 1900 <= year <= liveYear
    ):
        raise ValueError("Message year is required before filing")
    if year < liveYear:
        return _localDestination(owner, archive, decision["canonical"])
    return _imapDestination(owner, observedTarget, mappings, decision["canonical"])


def _barePublicSuffix(domain: str) -> bool:
    """Return whether a domain is a registry suffix rather than an organisation.

    Labels such as ``co`` and ``com`` are counted from the bundled ICANN
    section. A label that begins several suffixes is a registry designator, so
    ``co.uk`` cannot be saved. A one-off apex such as ``nhs.uk`` can.
    """
    if _PSL.publicsuffix(domain) != domain or _PSL_ICANN.publicsuffix(domain) != domain:
        return False
    labels = domain.split(".")
    return len(labels) == 1 or labels[0] in _registryLabels()


def _domainClarification(rules: dict, mailbox: str, host: str) -> str | None:
    value = (
        rules.get("mailboxes", {}).get(mailbox, {}).get("clarifications", {}).get(host)
    )
    return value if isinstance(value, str) else None


def _domainKey(domain: str) -> str:
    """Accept a confident registrable domain or a user-confirmed organisation."""
    chosen = _hostKey(domain)
    extracted = filingDomainExtract("sender@" + chosen)
    if extracted not in (None, chosen) or _barePublicSuffix(chosen):
        raise ValueError("Invalid filing domain")
    return chosen


def _domainLabelsOk(domain: str) -> bool:
    labels = domain.split(".")
    return len(labels) >= 2 and all(_labelOk(label) for label in labels)


def _hostKey(domain: str) -> str:
    if not isinstance(domain, str):
        raise ValueError("Invalid filing domain")
    chosen = domain.strip().lower().rstrip(".")
    if "@" in chosen or not _domainLabelsOk(chosen):
        raise ValueError("Invalid filing domain")
    return chosen


def _domainRule(rules: dict, mailbox: str, domain: str) -> dict | None:
    decision = (
        rules.get("mailboxes", {}).get(mailbox, {}).get("domains", {}).get(domain)
    )
    return dict(decision) if isinstance(decision, dict) else None


def _emptyMailbox() -> dict:
    return {
        "domains": {},
        "senders": {},
        "proposedParents": [],
        "clarifications": {},
    }


def _emptyRules() -> dict:
    return {"schemaVersion": _SCHEMA_VERSION, "mailboxes": {}}


def _existingSpelling(label: str, folders: list) -> str | None:
    spellings = []
    for folder in folders:
        path = folder.get("path") if isinstance(folder, dict) else None
        if not isinstance(path, str) or not path:
            continue
        leaf = path.rsplit("/", 1)[-1]
        if leaf.casefold() == label.casefold():
            spellings.append(leaf)
    unique = list(dict.fromkeys(spellings))
    if len(unique) == 1:
        return unique[0]
    return None


def _filingWrite(data: dict, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    temporaryName = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", dir=path.parent, delete=False
        ) as temporary:
            temporary.write(payload)
            temporaryName = temporary.name
        os.chmod(temporaryName, 0o600)
        os.replace(temporaryName, path)
        temporaryName = None
    finally:
        if temporaryName:
            os.unlink(temporaryName)
    return data


def _historyDecision(
    sender: str | None, mappings: list, index: dict
) -> tuple[dict, str] | None:
    classification = senderClassify(sender, mappings, index)
    if (
        not classification
        or classification.get("confidence") != "high"
        or classification.get("method") not in _SAFE_HISTORY
    ):
        return None
    canonical = classification["mapping"]["canonical"]
    parts = [part for part in canonical.split("/") if part]
    if len(parts) < 2:
        return None
    decision = dict(
        parent=parts[0],
        child=parts[-1],
        canonical=canonical,
        parentProposed=False,
    )
    return decision, classification.get("reason", "Archive history")


def _imapDestination(
    owner: dict, observed: dict, mappings: list, canonical: str
) -> tuple[dict, bool]:
    matches = [mapping for mapping in mappings if mapping["canonical"] == canonical]
    if len(matches) > 1:
        raise ValueError("Multiple server folders match the canonical folder")
    if len(matches) == 1:
        mapping = matches[0]
        if (
            mapping.get("issue")
            or not mapping.get("imap")
            or (mapping.get("imapExists") and not mapping.get("imapSelectable"))
        ):
            raise ValueError(
                mapping.get("issue", "IMAP target cannot receive messages")
            )
        destination = dict(
            kind="imap",
            mailbox=owner["id"],
            folder=mapping["imap"],
            exists=bool(mapping.get("imapExists")),
        )
        return destination, destination["exists"] is False
    return _imapMirrorPropose(owner, observed, canonical)


def _imapMirrorPropose(
    owner: dict, observed: dict, canonical: str
) -> tuple[dict, bool]:
    from mailAgent.migrationPlanning import _imapNameEncode

    folders = observed.get("folders", [])
    delimiters = {
        folder.get("delimiter")
        for folder in folders
        if folder.get("delimiter") is not None
    }
    if len(delimiters) != 1:
        raise ValueError("Cannot infer a safe server delimiter for the mirror")
    delimiter = next(iter(delimiters))
    parts = canonical.split("/")
    if any(delimiter in part for part in parts):
        raise ValueError("Cannot infer a safe server delimiter for the mirror")
    proposed = _imapNameEncode(delimiter.join(parts))
    if any(folder.get("path") == proposed for folder in folders):
        raise ValueError("Proposed mirror collides with an existing folder")
    return (
        dict(kind="imap", mailbox=owner["id"], folder=proposed, exists=False),
        True,
    )


def _labelOk(label: str) -> bool:
    return bool(
        label
        and label[0].isalnum()
        and label[-1].isalnum()
        and all(char.isalnum() or char == "-" for char in label)
    )


def _localDestination(owner: dict, archive: dict, canonical: str) -> tuple[dict, bool]:
    matches = [
        folder
        for folder in archive.get("folders", [])
        if folder.get("path") == canonical
    ]
    if len(matches) > 1:
        raise ValueError("Multiple archive folders match the canonical folder")
    if len(matches) == 1 and not matches[0].get("selectable"):
        raise ValueError("Canonical folder has no local message store")
    if len(matches) == 1:
        destination = dict(
            kind="local",
            mailbox=owner["id"],
            folder=canonical,
            path=matches[0].get("storage"),
            format=archive.get("format", "thunderbird"),
            exists=True,
        )
        return destination, False
    return (
        dict(
            kind="local",
            mailbox=owner["id"],
            folder=canonical,
            path=None,
            format=archive.get("format", "thunderbird"),
            exists=False,
        ),
        True,
    )


def _mailboxCheck(mailbox: str) -> None:
    if (
        not isinstance(mailbox, str)
        or not mailbox.strip()
        or any(ord(char) < 32 for char in mailbox)
    ):
        raise ValueError("Invalid filing mailbox")


def _mailboxEntry(data: dict, mailbox: str) -> dict:
    entry = data["mailboxes"].setdefault(mailbox, _emptyMailbox())
    entry.setdefault("domains", {})
    entry.setdefault("senders", {})
    entry.setdefault("proposedParents", [])
    entry.setdefault("clarifications", {})
    return entry


def _mappingsFor(owner: dict, observed: dict, archive: dict) -> tuple[list, dict]:
    if not _archiveUsable(archive):
        return [], {}
    from mailAgent.migrationPlanning import folderMappingsBuild

    mappings = folderMappingsBuild(
        dict(id=owner["id"], folderMappings=owner.get("folderMappings", {})),
        observed,
        archive,
    )
    return mappings, archiveSenderIndex(archive)


def _messageFile(
    account: dict,
    owner: dict,
    message: dict,
    archive: dict,
    rules: dict,
    prepared: dict,
    plan: dict,
    grouped: dict,
) -> None:
    folder = message.get("folder")
    if not isinstance(folder, str) or folder.lower() != "inbox":
        return
    sender = message.get("sender")
    domain, uncertain = _organisationDomain(sender, rules, owner["id"])
    if not domain:
        if message.get("seen") is True:
            _reviewAppend(
                plan,
                account["id"],
                folder,
                "Sender has no registrable domain",
                message,
            )
        return
    bucket = grouped.setdefault(
        (owner["id"], domain),
        dict(owner=owner, messages=[], eligible=[], uncertain=False),
    )
    bucket["uncertain"] = bucket["uncertain"] or uncertain
    bucket["messages"].append(message)
    if message.get("seen") is not True:
        return
    if uncertain and not _senderRule(rules, owner["id"], sender):
        _reviewAppend(
            plan,
            account["id"],
            folder,
            "Domain needs clarification",
            message,
            domain,
        )
        bucket["eligible"].append(dict(message=message, decision=None, source=""))
        return
    _messagePropose(
        account, owner, message, folder, domain, archive, rules, prepared, plan, bucket
    )


def _messagePropose(
    account: dict,
    owner: dict,
    message: dict,
    folder: str,
    domain: str,
    archive: dict,
    rules: dict,
    prepared: dict,
    plan: dict,
    bucket: dict,
) -> None:
    sender = message.get("sender")
    decision, source, evidence = _messageResolve(
        owner, sender, domain, rules, prepared, archive
    )
    if not decision:
        _reviewAppend(
            plan,
            account["id"],
            folder,
            "No safe canonical destination",
            message,
            domain,
        )
        bucket["eligible"].append(dict(message=message, decision=None, source=""))
        return
    try:
        observed = _observed(prepared["snapshot"], owner["id"])
        mappings = prepared["history"][owner["id"]][0]
        destination, create = _destinationBuild(
            decision, message, owner, observed, archive, mappings
        )
    except ValueError as error:
        _reviewAppend(plan, account["id"], folder, str(error), message, domain)
        bucket["eligible"].append(dict(message=message, decision=None, source=""))
        return
    bucket["eligible"].append(dict(message=message, decision=decision, source=source))
    plan["proposals"].append(
        _proposalBuild(
            account, message, domain, decision, source, evidence, destination, create
        )
    )


def _messageResolve(
    owner: dict,
    sender: str | None,
    domain: str,
    rules: dict,
    prepared: dict,
    archive: dict,
) -> tuple[dict | None, str, str]:
    if owner["id"] not in prepared["history"]:
        observed = _observed(prepared["snapshot"], owner["id"])
        prepared["history"][owner["id"]] = _mappingsFor(owner, observed, archive)
    senderRule = _senderRule(rules, owner["id"], sender)
    if senderRule:
        return (
            senderRule,
            "sender",
            f"Exact sender filing rule for {senderNormalize(sender)}",
        )
    domainRule = _domainRule(rules, owner["id"], domain)
    if domainRule:
        return domainRule, "domain", f"Domain filing rule for {domain}"
    mappings, index = prepared["history"][owner["id"]]
    found = _historyDecision(sender, mappings, index)
    if not found:
        return None, "", ""
    decision, reason = found
    return decision, "archive history", reason


def _organisationDomain(
    sender: str | None, rules: dict, mailbox: str
) -> tuple[str | None, bool]:
    """Return the grouping domain and whether the user still has to confirm it."""
    host = _senderHost(sender)
    if not host:
        return None, False
    clarified = _domainClarification(rules, mailbox, host)
    if clarified:
        return clarified, False
    extracted = filingDomainExtract(sender)
    if extracted:
        return extracted, False
    if _domainRule(rules, mailbox, host):
        return host, False
    return host, True


def _observed(snapshot: dict, mailbox: str) -> dict:
    for observed in snapshot.get("mailboxes", []):
        if observed.get("id") == mailbox:
            return observed
    return {}


def _overridesCollect(plan: dict, rules: dict) -> None:
    for mailbox, entry in sorted(rules.get("mailboxes", {}).items()):
        senders = entry.get("senders", {}) if isinstance(entry, dict) else {}
        for sender, decision in sorted(senders.items()):
            plan["senderOverrides"].append(
                dict(
                    mailbox=mailbox,
                    sender=sender,
                    parent=decision["parent"],
                    folder=decision["child"],
                    canonical=decision["canonical"],
                    parentProposed=decision["parentProposed"],
                )
            )


def _ownerAccount(account: dict, accounts: dict) -> dict | None:
    if account.get("role") == "personal":
        owner = accounts.get(account["id"])
    elif account.get("role") == "legacy":
        owner = accounts.get(account.get("migrationTarget"))
    else:
        owner = None
    if not owner or owner.get("role") != "personal":
        return None
    return owner


def _pathParts(canonical: str) -> tuple[str, str]:
    parts = [part for part in canonical.split("/") if part]
    if not parts:
        return "", ""
    return parts[0], parts[-1]


def _planEmpty(context: dict, snapshot: dict) -> dict:
    return dict(
        schemaVersion=_SCHEMA_VERSION,
        executionEnabled=False,
        liveYear=context["liveYear"],
        inboxScanned=any(
            isinstance(mailbox, dict) and "inboxInventory" in mailbox
            for mailbox in snapshot.get("mailboxes", [])
        ),
        rows=[],
        parents={},
        proposedParents={},
        proposals=[],
        reviews=[],
        excluded=[],
        senderOverrides=[],
    )


def _proposalBuild(
    account: dict,
    message: dict,
    domain: str,
    decision: dict,
    source: str,
    evidence: str,
    destination: dict,
    create: bool,
) -> dict:
    kind = destination.get("kind")
    return dict(
        source=dict(
            mailbox=account["id"],
            folder=message.get("folder"),
            uid=message.get("uid"),
            uidValidity=message.get("uidValidity"),
            sender=message.get("sender"),
            domain=domain,
            seen=True,
        ),
        readState="read",
        year=message.get("year"),
        canonical=decision["canonical"],
        destination=destination,
        decisionSource=source,
        evidence=evidence,
        requiresFolderCreation=create,
        executionPermitted=False,
        sourceRemovalAllowed=False,
        removalPolicy="copy-verify-remove" if kind == "local" else "imap-move",
    )


def _proposalSort(proposal: dict) -> tuple:
    source = proposal["source"]
    uid = str(source.get("uid", ""))
    return (
        source.get("mailbox", ""),
        int(uid) if uid.isdigit() else uid,
        source.get("sender", ""),
    )


def _proposedCollect(plan: dict, rules: dict) -> None:
    """Union stored proposed parents with rule parents absent from the archive."""
    for mailbox, parents in plan["parents"].items():
        discovered = set(parents)
        entry = rules.get("mailboxes", {}).get(mailbox, {})
        names = []
        if isinstance(entry, dict):
            names.extend(entry.get("proposedParents", []))
            for kind in ("domains", "senders"):
                for decision in entry.get(kind, {}).values():
                    parent = (
                        decision.get("parent") if isinstance(decision, dict) else None
                    )
                    if isinstance(parent, str):
                        names.append(parent)
        plan["proposedParents"][mailbox] = sorted(
            {name for name in names if name not in discovered},
            key=str.casefold,
        )


@lru_cache(maxsize=1)
def _registryLabels() -> frozenset[str]:
    """Return ICANN suffix labels that name a registry rather than one organisation."""
    text = (
        files("publicsuffixlist")
        .joinpath("public_suffix_list.dat")
        .read_text(encoding="utf-8")
    )
    counts: dict[str, int] = {}
    icann = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "// ===BEGIN ICANN DOMAINS===":
            icann = True
            continue
        if stripped == "// ===END ICANN DOMAINS===":
            break
        if not icann or not stripped or stripped.startswith("//"):
            continue
        rule = stripped.split()[0].lstrip("!*.")
        if "." not in rule:
            continue
        label = rule.split(".", 1)[0]
        counts[label] = counts.get(label, 0) + 1
    return frozenset(label for label, count in counts.items() if count >= 3)


def _reviewAppend(
    plan: dict,
    mailbox: str,
    folder: str,
    reason: str,
    message: dict | None = None,
    domain: str | None = None,
) -> None:
    source = dict(mailbox=mailbox, folder=folder or "INBOX")
    if message:
        source.update(
            uid=message.get("uid"),
            uidValidity=message.get("uidValidity"),
            sender=message.get("sender"),
            domain=domain or filingDomainExtract(message.get("sender")),
            seen=message.get("seen") is True,
        )
    plan["reviews"].append(
        dict(
            source=source,
            readState="read" if message and message.get("seen") is True else "",
            reason=reason,
            executionPermitted=False,
        )
    )


def _reviewSort(review: dict) -> tuple:
    source = review["source"]
    uid = str(source.get("uid", ""))
    return (
        source.get("mailbox", ""),
        int(uid) if uid.isdigit() else uid,
        review["reason"],
    )


def _rowsBuild(grouped: dict, rules: dict, prepared: dict, plan: dict) -> None:
    for (mailbox, domain), bucket in grouped.items():
        owner = bucket["owner"]
        archive = prepared["archives"][mailbox]
        folders = archive.get("folders", [])
        parents = plan["parents"].get(mailbox, [])
        decision, source = _rowDecision(rules, mailbox, domain, bucket["eligible"])
        parent, folder, canonical = "", "", ""
        if decision:
            canonical = decision.get("canonical", "")
            parent, folder = _pathParts(canonical)
        plan["rows"].append(
            dict(
                mailbox=mailbox,
                archive=owner.get("archiveName") or mailbox,
                domain=domain,
                inboxCount=len(bucket["messages"]),
                parent=parent,
                folder=folder if decision else "",
                canonical=canonical if decision else "",
                status=filingStatus(decision, parents, folders),
                decisionSource=source,
                suggestion=filingChildSuggest(domain, folders),
                domainUncertain=bucket.get("uncertain", False),
            )
        )


def _rowDecision(
    rules: dict, mailbox: str, domain: str, eligible: list
) -> tuple[dict | None, str]:
    domainRule = _domainRule(rules, mailbox, domain)
    if domainRule:
        return domainRule, "domain"
    decided = [item for item in eligible if item.get("decision")]
    if not eligible or len(decided) != len(eligible):
        return None, ""
    canonicals = {item["decision"]["canonical"] for item in decided}
    sources = {item["source"] for item in decided}
    if len(canonicals) != 1:
        return None, ""
    source = sources.pop() if len(sources) == 1 else "archive history"
    return dict(decided[0]["decision"]), source


def _rulesValidate(data: dict) -> None:
    if not isinstance(data, dict) or data.get("schemaVersion") != _SCHEMA_VERSION:
        raise ValueError("Unsupported filing-rules schema")
    if _secretKey(data):
        raise ValueError("Filing rules must not contain secrets or message content")
    mailboxes = data.get("mailboxes")
    if not isinstance(mailboxes, dict):
        raise ValueError("Invalid filing-rules mailboxes")
    for mailbox, entry in mailboxes.items():
        _mailboxCheck(mailbox)
        if not isinstance(entry, dict):
            raise ValueError("Invalid filing-rules mailbox")
        domains = entry.get("domains", {})
        senders = entry.get("senders", {})
        proposed = entry.get("proposedParents", [])
        clarifications = entry.get("clarifications", {})
        if (
            not isinstance(domains, dict)
            or not isinstance(senders, dict)
            or not isinstance(proposed, list)
            or not isinstance(clarifications, dict)
        ):
            raise ValueError("Invalid filing-rules mailbox")
        for domain, decision in domains.items():
            if domain != _domainKey(domain):
                raise ValueError("Invalid filing domain")
            _decisionValidate(decision)
        for host, chosen in clarifications.items():
            if host != _hostKey(host) or filingDomainExtract("sender@" + host):
                raise ValueError("Invalid filing domain")
            if chosen != _domainKey(chosen):
                raise ValueError("Invalid filing domain")
        for sender, decision in senders.items():
            if senderNormalize(sender) != sender:
                raise ValueError("Invalid filing sender override")
            _decisionValidate(decision)
        for name in proposed:
            if name != filingNameNormalize(name):
                raise ValueError("Invalid proposed parent")


def _secretKey(value) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in _SECRET_KEYS or _secretKey(item):
                return True
    elif isinstance(value, list):
        return any(_secretKey(item) for item in value)
    return False


def _senderHost(value: str | None) -> str | None:
    sender = senderNormalize(value)
    if not sender or "@" not in sender:
        return None
    host = sender.rsplit("@", 1)[1].strip().lower().rstrip(".")
    if not _domainLabelsOk(host):
        return None
    return host


def _senderRule(rules: dict, mailbox: str, sender: str | None) -> dict | None:
    normalized = senderNormalize(sender) if sender else None
    if not normalized:
        return None
    decision = (
        rules.get("mailboxes", {}).get(mailbox, {}).get("senders", {}).get(normalized)
    )
    return dict(decision) if isinstance(decision, dict) else None
