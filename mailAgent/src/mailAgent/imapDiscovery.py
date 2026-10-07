"""IMAP observation; never selects or mutates a mailbox."""

import re
from typing import Any

## discovery


def mailboxDiscover(client: Any, account: dict) -> dict:
    """Observe folders, counts and quota using an authenticated connection."""
    result = {key: account[key] for key in ("id", "name", "host", "username")}
    result.update(folders=[], quota=[], issues=[])
    status, rows = client.list()
    if status != "OK":
        raise ValueError("IMAP LIST failed")
    for row in rows or []:
        if row is None:
            continue
        try:
            folder = folderParse(row)
        except ValueError:
            result["issues"].append("Unsupported LIST response")
            continue
        if "\\noselect" not in [a.lower() for a in folder["attributes"]]:
            try:
                status, counts = client.status(
                    _pathQuote(folder["path"]), "(MESSAGES UNSEEN)"
                )
                if status == "OK":
                    for key, value in re.findall(
                        rb"(MESSAGES|UNSEEN)\s+(\d+)",
                        b" ".join(r for r in counts if isinstance(r, bytes)),
                    ):
                        folder[key.decode().lower()] = int(value)
            except Exception:
                # Server errors are recorded without authentication/server text.
                result["issues"].append("Folder counts unavailable")
        result["folders"].append(folder)
    capabilities = {
        c.decode().upper() if isinstance(c, bytes) else c.upper()
        for c in client.capabilities
    }
    if "QUOTA" in capabilities:
        try:
            status, data = client.getquotaroot("INBOX")
            if status == "OK":
                result["quota"] = quotaParse(data)
            else:
                result["issues"].append("Quota unavailable")
        except Exception:
            result["issues"].append("Quota unavailable")
    else:
        result["issues"].append("Quota unsupported")
    return result


## parsing


def folderParse(row: bytes | tuple) -> dict:
    """Parse quoted, atom and literal LIST paths preserving wire spelling."""
    literal = None
    if isinstance(row, tuple):
        row, literal = row
    match = re.fullmatch(rb'\((.*?)\)\s+(NIL|"(?:\\.|[^"\\])*")\s+(.+)', row)
    if not match:
        raise ValueError("Unsupported LIST syntax")
    attributes, delimiter, path = match.groups()
    raw = literal if literal is not None else path
    return {
        "path": (
            literal.decode("ascii", "surrogateescape")
            if literal is not None
            else _pathUnquote(path)
        ),
        "rawPath": raw.decode("ascii", "surrogateescape"),
        "delimiter": None if delimiter == b"NIL" else _pathUnquote(delimiter),
        "attributes": attributes.decode("ascii").split(),
    }


def quotaParse(data: list) -> list[dict]:
    """Extract quota resources including their server-defined units."""
    result = []
    for group in data:
        for row in group or []:
            if not isinstance(row, bytes):
                continue
            match = re.search(rb"^(.*?)\s+\((.*)\)$", row)
            if match:
                for resource, used, limit in re.findall(
                    rb"(\w+)\s+(\d+)\s+(\d+)", match[2]
                ):
                    result.append(
                        dict(
                            root=_pathUnquote(match[1]),
                            resource=resource.decode(),
                            used=int(used),
                            limit=int(limit),
                            unit="KiB" if resource == b"STORAGE" else "count",
                        )
                    )
    return result


def _pathQuote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _pathUnquote(value: bytes) -> str:
    if value.startswith(b'"') and value.endswith(b'"'):
        value = re.sub(rb'\\([\\"])', rb"\1", value[1:-1])
    return value.decode("ascii", "surrogateescape")
