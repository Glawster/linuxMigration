"""Persist user-selected digest preferences without changing mail."""

import json
import os
from pathlib import Path
import re
import tempfile

DEFAULT_INTEREST_FILE = Path.home() / ".config/mailAgent/interesting.json"

_DIGEST_SUBJECT_SIGNALS = (
    ("action required", "action required"),
    ("appointment", "appointment"),
    ("booking", "booking"),
    ("delivery", "delivery"),
    ("dispatch", "dispatch"),
    ("invoice", "invoice"),
    ("order", "order"),
    ("payment", "payment"),
    ("reminder", "reminder"),
    ("renewal", "renewal"),
    ("security", "security"),
    ("verification", "verification"),
    ("verify", "verification"),
)

_DIGEST_REASON_DEFAULTS = {
    "person": "in",
    "reminder": "in",
    "delivery": "out",
    "dispatch": "out",
    "order": "out",
    "payment": "out",
    "invoice": "out",
    "action required": "manual",
    "appointment": "manual",
    "booking": "manual",
    "renewal": "manual",
    "security": "manual",
    "verification": "manual",
}

_AUTOMATED_SENDER = re.compile(
    r"(?:^|[._+-])(no[-_. ]?reply|noreply|do[-_. ]?not[-_. ]?reply|newsletter|"
    r"notification|notify|billing|accounts?|support|service|customer|orders?|"
    r"delivery|dispatch|payments?|invoice|info|admin|marketing|news)(?:$|[._+-])",
    re.IGNORECASE,
)

_SENDER_POLICIES = ("auto", "in", "out")
_PERSON_POLICIES = ("auto", "yes", "no")


def _emptyPreferences() -> dict:
    return {
        "schemaVersion": 1,
        "mailboxes": {},
        "reasonPolicies": {},
        "senderPolicies": {},
        "personPolicies": {},
    }


def interestLoad(path: Path | None = None) -> dict:
    """Load digest preferences; missing files use safe defaults."""
    path = path or DEFAULT_INTEREST_FILE
    if not path.exists():
        return _emptyPreferences()
    data = json.loads(path.read_text())
    if (
        not isinstance(data, dict)
        or data.get("schemaVersion") != 1
        or not isinstance(data.get("mailboxes"), dict)
        or not isinstance(data.get("reasonPolicies", {}), dict)
        or not isinstance(data.get("senderPolicies", {}), dict)
        or not isinstance(data.get("personPolicies", {}), dict)
    ):
        raise ValueError("Unsupported interesting-sender preference file")
    if any(
        reason not in _DIGEST_REASON_DEFAULTS or policy not in ("in", "out", "manual")
        for reason, policy in data.get("reasonPolicies", {}).items()
    ):
        raise ValueError("Unsupported digest reason policy")
    _nestedPoliciesValidate(data.get("senderPolicies", {}), _SENDER_POLICIES)
    _nestedPoliciesValidate(data.get("personPolicies", {}), _PERSON_POLICIES)
    data.setdefault("reasonPolicies", {})
    data.setdefault("senderPolicies", {})
    data.setdefault("personPolicies", {})
    return data


def _nestedPoliciesValidate(values: dict, allowed: tuple[str, ...]) -> None:
    for mailbox, policies in values.items():
        if not isinstance(mailbox, str) or not isinstance(policies, dict):
            raise ValueError("Unsupported digest sender policy")
        if any(
            not isinstance(sender, str) or policy not in allowed
            for sender, policy in policies.items()
        ):
            raise ValueError("Unsupported digest sender policy")


def _legacyInterestIs(data: dict, mailbox: str, sender: str) -> bool:
    return _senderNormalize(sender) in data.get("mailboxes", {}).get(mailbox, [])


def interestIs(data: dict, mailbox: str, sender: str) -> bool:
    """Return whether the exact sender is explicitly included."""
    return interestSenderPolicyGet(data, mailbox, sender) == "in"


def interestReasons() -> tuple[str, ...]:
    """Return digest reasons in stable user-facing order."""
    return tuple(_DIGEST_REASON_DEFAULTS)


def interestReasonPolicies(data: dict) -> dict[str, str]:
    """Return effective reason policies including defaults not yet persisted."""
    return {
        reason: data.get("reasonPolicies", {}).get(reason, default)
        for reason, default in _DIGEST_REASON_DEFAULTS.items()
    }


def interestReasonSet(
    reason: str,
    policy: str,
    path: Path | None = None,
) -> dict:
    """Persist one digest reason policy without touching mailbox content."""
    reason = reason.strip().lower() if isinstance(reason, str) else ""
    policy = policy.strip().lower() if isinstance(policy, str) else ""
    if reason not in _DIGEST_REASON_DEFAULTS or policy not in ("in", "out", "manual"):
        raise ValueError("Invalid digest reason policy")
    path = path or DEFAULT_INTEREST_FILE
    data = interestLoad(path)
    data.setdefault("reasonPolicies", {})[reason] = policy
    return _interestWrite(data, path)


def interestSenderPolicyGet(data: dict, mailbox: str, sender: str) -> str:
    """Return Auto/In/Out policy for one sender, honoring legacy explicit includes."""
    sender = _senderNormalize(sender)
    explicit = data.get("senderPolicies", {}).get(mailbox, {}).get(sender)
    if explicit in _SENDER_POLICIES:
        return explicit
    return "in" if _legacyInterestIs(data, mailbox, sender) else "auto"


def interestSenderPolicySet(
    mailbox: str,
    sender: str,
    policy: str,
    path: Path | None = None,
) -> dict:
    """Persist an Auto/In/Out override for one sender."""
    sender = _senderNormalize(sender)
    policy = policy.strip().lower() if isinstance(policy, str) else ""
    if not sender or policy not in _SENDER_POLICIES:
        raise ValueError("Invalid digest sender policy")
    path = path or DEFAULT_INTEREST_FILE
    data = interestLoad(path)
    _legacyInterestRemove(data, mailbox, sender)
    values = data.setdefault("senderPolicies", {}).setdefault(mailbox, {})
    if policy == "auto":
        values.pop(sender, None)
    else:
        values[sender] = policy
    if not values:
        data["senderPolicies"].pop(mailbox, None)
    return _interestWrite(data, path)


def interestPersonPolicyGet(data: dict, mailbox: str, sender: str) -> str:
    """Return Auto/Yes/No person-classification override for one sender."""
    sender = _senderNormalize(sender)
    return data.get("personPolicies", {}).get(mailbox, {}).get(sender, "auto")


def interestPersonPolicySet(
    mailbox: str,
    sender: str,
    policy: str,
    path: Path | None = None,
) -> dict:
    """Persist an Auto/Yes/No override for person classification."""
    sender = _senderNormalize(sender)
    policy = policy.strip().lower() if isinstance(policy, str) else ""
    if not sender or policy not in _PERSON_POLICIES:
        raise ValueError("Invalid person classification policy")
    path = path or DEFAULT_INTEREST_FILE
    data = interestLoad(path)
    values = data.setdefault("personPolicies", {}).setdefault(mailbox, {})
    if policy == "auto":
        values.pop(sender, None)
    else:
        values[sender] = policy
    if not values:
        data["personPolicies"].pop(mailbox, None)
    return _interestWrite(data, path)


def interestSuggest(
    sender: str,
    subjects: list[str],
    senderName: str = "",
    personPolicy: str = "auto",
) -> tuple[bool, str]:
    """Classify a digest reason from transparent, lightweight Inbox signals."""
    text = " ".join(subject for subject in subjects if isinstance(subject, str)).lower()
    for needle, label in _DIGEST_SUBJECT_SIGNALS:
        if needle in text:
            return True, label
    if personPolicy == "yes":
        return True, "person"
    if personPolicy == "no":
        return False, ""
    if _personLikely(sender, senderName):
        return True, "person"
    return False, ""


def interestEffective(data: dict, mailbox: str, sender: str, reason: str) -> bool:
    """Return effective inclusion after sender override then reason policy."""
    senderPolicy = interestSenderPolicyGet(data, mailbox, sender)
    if senderPolicy == "in":
        return True
    if senderPolicy == "out":
        return False
    return interestReasonPolicies(data).get(reason, "manual") == "in"


def interestSet(
    mailbox: str,
    sender: str,
    interesting: bool,
    path: Path | None = None,
) -> dict:
    """Compatibility helper: True means In, False means Auto."""
    return interestSenderPolicySet(
        mailbox,
        sender,
        "in" if interesting else "auto",
        path,
    )


def _legacyInterestRemove(data: dict, mailbox: str, sender: str) -> None:
    values = set(data.get("mailboxes", {}).get(mailbox, []))
    values.discard(sender)
    if values:
        data.setdefault("mailboxes", {})[mailbox] = sorted(values)
    else:
        data.setdefault("mailboxes", {}).pop(mailbox, None)


def _interestWrite(data: dict, path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, delete=False
    ) as temporary:
        temporary.write(payload)
        temporaryName = temporary.name
    os.chmod(temporaryName, 0o600)
    os.replace(temporaryName, path)
    return data


def _personLikely(sender: str, senderName: str) -> bool:
    """Identify likely people conservatively from From name/address metadata."""
    if not senderName or not isinstance(senderName, str):
        return False
    local = _senderNormalize(sender).partition("@")[0]
    if not local or _AUTOMATED_SENDER.search(local):
        return False
    name = senderName.strip()
    if len(name.split()) < 2:
        return False
    lowered = name.lower()
    if any(
        token in lowered
        for token in (
            "team",
            "support",
            "service",
            "accounts",
            "newsletter",
            "notifications",
            "customer",
            "company",
            "limited",
            "ltd",
        )
    ):
        return False
    return True


def _senderNormalize(sender: str) -> str:
    return sender.strip().lower() if isinstance(sender, str) else ""
