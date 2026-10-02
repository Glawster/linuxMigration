"""Read Thunderbird metadata and filter files without changing profiles."""

import configparser
import re
from pathlib import Path


## discovery


def profilesDiscover(root: Path) -> list[dict]:
    """Find metadata-selected profiles; keep other profiles explicitly labelled."""
    metadata = configparser.ConfigParser()
    metadata.read(root / "profiles.ini")
    installs = configparser.ConfigParser()
    installs.read(root / "installs.ini")
    defaults = {
        section.get("Default")
        for section in installs.values()
        if section.get("Default")
    }
    defaults.update(
        section.get("Default")
        for name, section in metadata.items()
        if name.startswith("Install") and section.get("Default")
    )
    profiles = []
    for name in metadata.sections():
        if not name.startswith("Profile"):
            continue
        section = metadata[name]
        if not section.get("Path"):
            continue
        path = Path(section["Path"])
        if section.get("IsRelative", "1") == "1":
            path = root / path
        if path.is_dir():
            profiles.append(
                dict(
                    path=str(path.resolve()),
                    default=section.get("Default") == "1"
                    or section["Path"] in defaults,
                )
            )
    return profiles


def sourcesDiscover(root: Path) -> list[dict]:
    """Read IMAP and POP account filters from all metadata-listed profiles."""
    result = []
    for profile in profilesDiscover(root):
        prefs = Path(profile["path"]) / "prefs.js"
        settings = {}
        if prefs.is_file():
            for key, value in re.findall(
                r'user_pref\("(mail\.server\.[^"]+)",\s*"((?:\\.|[^"\\])*)"\);',
                prefs.read_text(errors="replace"),
            ):
                settings[key] = _valueUnescape(value)
        for kind in ("ImapMail", "Mail"):
            for path in sorted(
                (Path(profile["path"]) / kind).glob("*/msgFilterRules.dat")
            ):
                servers = []
                for key, value in settings.items():
                    if (
                        key.endswith(".directory")
                        and Path(value).resolve() == path.parent.resolve()
                    ):
                        servers.append(key.removesuffix(".directory"))
                    if (
                        key.endswith(".directory-rel")
                        and value == f"[ProfD]{kind}/{path.parent.name}"
                    ):
                        servers.append(key.removesuffix(".directory-rel"))
                identities = [
                    {
                        "host": settings.get(server + ".hostname"),
                        "username": settings.get(server + ".userName"),
                    }
                    for server in sorted(set(servers))
                ]
                result.append(
                    dict(
                        profile=profile,
                        path=str(path),
                        kind=kind,
                        account=path.parent.name,
                        identities=identities,
                        filters=filtersParse(path.read_text(errors="replace")),
                    )
                )
    return result


## parsing


def filtersParse(content: str) -> list[dict]:
    """Preserve filter conditions and unsupported constructs for audit."""
    result = []
    current = None
    pending = None
    for line in content.splitlines():
        match = re.fullmatch(r'(\w+)="((?:\\.|[^"\\])*)"', line)
        if match and match[1] == "name":
            current = dict(
                name=_valueUnescape(match[2]),
                enabled=None,
                conditions=[],
                actions=[],
                destinations=[],
                raw=[],
                issues=[],
            )
            result.append(current)
            pending = None
        if current is None:
            if line and not (match and match[1] in ("version", "logging")):
                current = dict(
                    name="Unsupported preamble",
                    enabled=None,
                    conditions=[],
                    actions=[],
                    destinations=[],
                    raw=[],
                    issues=[],
                )
                result.append(current)
            else:
                continue
        current["raw"].append(line)
        if not match:
            current["issues"].append("Unsupported filter syntax: " + line)
            continue
        key, value = match[1], _valueUnescape(match[2])
        if key == "enabled":
            current["enabled"] = value == "yes" if value in ("yes", "no") else None
            if current["enabled"] is None:
                current["issues"].append("Unsupported enabled value")
        elif key == "condition":
            current["conditions"].append(value)
            if value != "ALL" and not re.fullmatch(
                r"(?:AND|OR)\s*\(.+\)(?:\s*(?:AND|OR)\s*\(.+\))*", value
            ):
                current["issues"].append("Unsupported condition syntax")
        elif key == "action":
            pending = dict(type=value, value=None)
            current["actions"].append(pending)
            if value not in (
                "Move to folder",
                "Copy to folder",
                "Mark read",
                "Mark unread",
                "Delete",
                "Stop execution",
                "JunkScore",
                "AddTag",
                "Change priority",
            ):
                current["issues"].append("Unsupported action: " + value)
        elif key == "actionValue":
            if pending is None:
                current["issues"].append("Action value without action")
            else:
                pending["value"] = value
                if pending["type"] in ("Move to folder", "Copy to folder"):
                    current["destinations"].append(value)
        elif key == "type":
            current["trigger"] = value
        elif key != "name":
            current["issues"].append("Unsupported field: " + key)
    return result


def _valueUnescape(value: str) -> str:
    return re.sub(r'\\([\\"])', r"\1", value)
