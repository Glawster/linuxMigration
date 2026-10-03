"""Durable user decisions that refine migration planning without changing mail."""

import json
import os
from pathlib import Path

from mailAgent.senderAddress import senderNormalize

_SCHEMA_VERSION = 1


def resolutionPath() -> Path:
    """Return the default durable plan-resolution preference path."""
    return Path.home() / ".config/mailAgent/plan-resolution.json"


def resolutionLoad(path: Path | None = None) -> dict:
    """Load and validate plan-resolution preferences."""
    path = path or resolutionPath()
    if not path.is_file():
        return {"schemaVersion": _SCHEMA_VERSION, "senderMappings": {}}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("schemaVersion") != _SCHEMA_VERSION:
        raise ValueError("Unsupported plan-resolution schema")
    mappings = data.get("senderMappings")
    if not isinstance(mappings, dict):
        raise ValueError("Invalid senderMappings in plan-resolution storage")
    for mailbox, senders in mappings.items():
        if not isinstance(mailbox, str) or not mailbox or not isinstance(senders, dict):
            raise ValueError("Invalid senderMappings in plan-resolution storage")
        for sender, decision in senders.items():
            if (
                not isinstance(sender, str)
                or not sender
                or not isinstance(decision, dict)
                or not isinstance(decision.get("targetMailbox"), str)
                or not decision["targetMailbox"]
                or not isinstance(decision.get("canonical"), str)
                or not decision["canonical"]
            ):
                raise ValueError("Invalid sender decision in plan-resolution storage")
    return data


def senderResolutionGet(
    data: dict, sourceMailbox: str, sender: str | None
) -> dict | None:
    """Return a sender-specific resolution decision when one exists."""
    normalized = senderNormalize(sender) if sender else None
    if not normalized:
        return None
    return data.get("senderMappings", {}).get(sourceMailbox, {}).get(normalized)


def senderResolutionSet(
    sourceMailbox: str,
    sender: str,
    targetMailbox: str,
    canonical: str,
    path: Path | None = None,
) -> dict:
    """Persist one explicit sender-to-canonical-folder decision atomically."""
    normalized = senderNormalize(sender)
    if not normalized or not sourceMailbox or not targetMailbox or not canonical:
        raise ValueError("Sender resolution requires mailbox, sender and canonical folder")
    if (
        any(part in ("", ".", "..") for part in canonical.split("/"))
        or any(ord(char) < 32 for char in canonical)
    ):
        raise ValueError("Invalid canonical folder")
    path = path or resolutionPath()
    data = resolutionLoad(path)
    data.setdefault("senderMappings", {}).setdefault(sourceMailbox, {})[normalized] = {
        "targetMailbox": targetMailbox,
        "canonical": canonical,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    return data
