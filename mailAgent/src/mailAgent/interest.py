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


def interestLoad(path: Path | None = None) -> dict:
    """Load sender and reason preferences; missing files use safe defaults."""
    path = path or DEFAULT_INTEREST_FILE
    if not path.exists():
        return {"schemaVersion": 1, "mailboxes": {}, "reasonPolicies": {}}
    data = json.loads(path.read_text())
    if (
        not isinstance(data, dict)
        or data.get("schemaVersion") != 1
        or not isinstance(data.get("mailboxes"), dict)
        or not isinstance(data.get("reasonPolicies", {}), dict)
    ):
        raise ValueError("Unsupported interesting-sender preference file")
    if any(
        reason not in _DIGEST_REASON_DEFAULTS or policy not in ("in", "out", "manual")
        for reason, policy in data.get("reasonPolicies", {}).items()
    ):
        raise ValueError("Unsupported digest reason policy")
    data.setdefault("reasonPolicies", {})
    return data


def interestIs(data: dict, mailbox: str, sender: str) -> bool:
    """Return whether the exact normalized sender is manually included."""
    return _senderNormalize(sender) in data.get("mailboxes", {}).get(mailbox, [])


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


def interestSuggest(
    sender: str,
    subjects: list[str],
    senderName: str = "",
) -> tuple[bool, str]:
    """Classify a digest reason from transparent, lightweight Inbox signals."""
    text = " ".join(subject for subject in subjects if isinstance(subject, str)).lower()
    for needle, label in _DIGEST_SUBJECT_SIGNALS:
        if needle in text:
            return True, label
    if _personLikely(sender, senderName):
        return True, "person"
    return False, ""


def interestEffective(data: dict, mailbox: str, sender: str, reason: str) -> bool:
    """Return effective digest inclusion; an explicit sender include wins."""
    if interestIs(data, mailbox, sender):
        return True
    return interestReasonPolicies(data).get(reason, "manual") == "in"


def interestSet(
    mailbox: str,
    sender: str,
    interesting: bool,
    path: Path | None = None,
) -> dict:
    """Persist an exact sender include preference atomically."""
    path = path or DEFAULT_INTEREST_FILE
    sender = _senderNormalize(sender)
    if not sender:
        raise ValueError("Cannot mark an empty sender")
    data = interestLoad(path)
    mailboxes = data.setdefault("mailboxes", {})
    values = set(mailboxes.get(mailbox, []))
    if interesting:
        values.add(sender)
    else:
        values.discard(sender)
    if values:
        mailboxes[mailbox] = sorted(values)
    else:
        mailboxes.pop(mailbox, None)
    return _interestWrite(data, path)


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
