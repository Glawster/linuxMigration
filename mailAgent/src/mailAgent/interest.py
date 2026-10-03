"""Persist user-selected interesting senders without changing mail."""

import json
import os
from pathlib import Path
import tempfile

DEFAULT_INTEREST_FILE = Path.home() / ".config/mailAgent/interesting.json"


def interestLoad(path: Path | None = None) -> dict:
    """Load sender-interest preferences; missing files mean no selections."""
    path = path or DEFAULT_INTEREST_FILE
    if not path.exists():
        return {"schemaVersion": 1, "mailboxes": {}}
    data = json.loads(path.read_text())
    if (
        not isinstance(data, dict)
        or data.get("schemaVersion") != 1
        or not isinstance(data.get("mailboxes"), dict)
    ):
        raise ValueError("Unsupported interesting-sender preference file")
    return data


def interestIs(data: dict, mailbox: str, sender: str) -> bool:
    """Return whether the exact normalized sender is marked interesting."""
    return _senderNormalize(sender) in data.get("mailboxes", {}).get(mailbox, [])


def interestSet(
    mailbox: str,
    sender: str,
    interesting: bool,
    path: Path | None = None,
) -> dict:
    """Persist an exact sender preference atomically."""
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


def _senderNormalize(sender: str) -> str:
    return sender.strip().lower() if isinstance(sender, str) else ""
