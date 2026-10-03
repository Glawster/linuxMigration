"""Collect Date headers and stable message identities over read-only IMAP."""

import re
from email.header import decode_header, make_header
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any

## inventory


def messagesDiscover(client: Any, folders: list[dict], batchSize: int = 200) -> dict:
    """Inspect personal/legacy messages using EXAMINE and BODY.PEEK headers."""
    if batchSize < 1:
        raise ValueError("batchSize must be positive")
    result = dict(messages=[], issues=[], complete=True)
    for folder in folders:
        if "\\noselect" in [attribute.lower() for attribute in folder["attributes"]]:
            continue
        if folderSystemKind(folder) in ("trash", "junk", "drafts"):
            continue
        try:
            _folderInspect(client, folder, batchSize, result)
        except Exception:
            result["complete"] = False
            result["issues"].append(
                dict(
                    folder=folder["path"],
                    message="Message inventory unavailable or incomplete",
                )
            )
    return result


def inboxMessagesDiscover(
    client: Any, folders: list[dict], batchSize: int = 200
) -> dict:
    """Inspect Inbox headers for the interactive interesting-sender view."""
    inbox = [
        folder
        for folder in folders
        if folder["path"].lower() == "inbox"
        or "\\inbox" in [attribute.lower() for attribute in folder["attributes"]]
    ]
    result = dict(messages=[], issues=[], complete=True)
    for folder in inbox:
        try:
            _folderInspect(client, folder, batchSize, result)
        except Exception:
            result["complete"] = False
            result["issues"].append(
                dict(
                    folder=folder["path"],
                    message="Inbox inventory unavailable or incomplete",
                )
            )
    return result


## parsing


def folderSystemKind(folder: dict) -> str | None:
    """Identify special-use folders or conventional folder leaf names."""
    attributes = {a.lower() for a in folder["attributes"]}
    for kind in ("trash", "junk", "drafts", "sent"):
        if "\\" + kind in attributes:
            return kind
    delimiter = folder.get("delimiter")
    leaf = folder["path"].rsplit(delimiter, 1)[-1] if delimiter else folder["path"]
    return {
        "trash": "trash",
        "junk": "junk",
        "spam": "junk",
        "drafts": "drafts",
        "sent": "sent",
        "sent items": "sent",
        "sent mail": "sent",
    }.get(leaf.lower())


def messageParse(metadata: bytes, header: bytes, folder: str, uidValidity: str) -> dict:
    """Parse stable identity plus lightweight headers; never inspect the body."""
    uid = re.search(rb"\bUID\s+(\d+)\b", metadata)
    if not uid:
        raise ValueError("Missing UID in FETCH response")
    result = dict(
        folder=folder,
        uid=uid[1].decode(),
        uidValidity=uidValidity,
        year=None,
        sender=None,
        subject="",
    )
    parsed = BytesParser().parsebytes(header)
    dates = parsed.get_all("Date", [])
    senders = [
        address.lower()
        for _, address in getaddresses(parsed.get_all("From", []))
        if address
    ]
    if len(senders) == 1:
        result["sender"] = senders[0]
    subject = parsed.get("Subject")
    if subject:
        try:
            result["subject"] = str(make_header(decode_header(subject)))
        except (LookupError, UnicodeError):
            result["subject"] = str(subject)
    try:
        if len(dates) != 1:
            raise ValueError("Missing or duplicate Date header")
        date = parsedate_to_datetime(dates[0])
        result["year"] = date.year
    except (ValueError, TypeError, OverflowError):
        result["issue"] = "Missing, invalid or ambiguous Date header"
    return result


## utilities


def _folderInspect(client: Any, folder: dict, batchSize: int, result: dict) -> None:
    path = folder["path"]
    quoted = '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'
    status, _ = client.select(quoted, readonly=True)
    if status != "OK":
        raise ValueError("Cannot examine folder")
    _, validity = client.response("UIDVALIDITY")
    if not validity or not isinstance(validity[0], bytes) or not validity[0].isdigit():
        raise ValueError("UIDVALIDITY unavailable")
    status, rows = client.uid("SEARCH", None, "ALL")
    if status != "OK" or not rows or not isinstance(rows[0], bytes):
        raise ValueError("UID SEARCH failed")
    identifiers = rows[0].split()
    if any(not uid.isdigit() for uid in identifiers):
        raise ValueError("Invalid UID SEARCH response")
    for start in range(0, len(identifiers), batchSize):
        batch = identifiers[start : start + batchSize]
        status, rows = client.uid(
            "FETCH",
            b",".join(batch).decode(),
            "(UID BODY.PEEK[HEADER.FIELDS (DATE FROM SUBJECT)])",
        )
        if status != "OK":
            raise ValueError("UID FETCH failed")
        observed = set()
        for row in rows or []:
            if isinstance(row, tuple) and len(row) == 2:
                message = messageParse(row[0], row[1], path, validity[0].decode())
                if message["uid"].encode() not in batch or message["uid"] in observed:
                    raise ValueError("Unexpected or duplicate UID")
                observed.add(message["uid"])
                result["messages"].append(message)
        if observed != {uid.decode() for uid in batch}:
            raise ValueError("Messages changed during inventory; rescan required")
