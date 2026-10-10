"""Validate explicit mailbox roles and independent connection settings."""

from copy import deepcopy
from pathlib import Path

ROLES = {"personal", "legacy", "shared", "support"}

## configuration


def configValidate(config: dict, base: Path) -> dict:
    """Return normalized configuration without creating archive directories."""
    result = deepcopy(config)
    if not isinstance(result, dict):
        raise ValueError("Configuration must be an object")
    general = result.setdefault("general", {})
    if not isinstance(general, dict):
        raise ValueError("general must be an object")
    if type(general.setdefault("credentialsSessionCache", False)) is not bool:
        raise ValueError("credentialsSessionCache must be true or false")
    year = general.setdefault("liveYear", 2026)
    if type(year) is not int or not 1900 <= year <= 9999:
        raise ValueError("liveYear must be a year between 1900 and 9999")
    if "credentialsFile" in general:
        value = general["credentialsFile"]
        if (
            not isinstance(value, str)
            or not value.strip()
            or any(ord(char) < 32 for char in value)
        ):
            raise ValueError("Invalid credentialsFile")
        path = Path(value).expanduser()
        general["credentialsFile"] = str(
            (base / path).absolute() if not path.is_absolute() else path.absolute()
        )
    accounts = result.get("mailboxes")
    if not isinstance(accounts, list) or not accounts:
        raise ValueError("Configure at least one mailbox")
    identifiers = set()
    for account in accounts:
        _accountValidate(account, identifiers, base)
    indexed = {account["id"]: account for account in accounts}
    for account in accounts:
        if account["role"] == "legacy":
            _legacyValidate(account, indexed)
    return result


## utilities


def _accountValidate(account: dict, identifiers: set, base: Path) -> None:
    if not isinstance(account, dict):
        raise ValueError("Mailbox must be an object")
    for key in ("id", "name", "host", "username", "role"):
        if (
            not isinstance(account.get(key), str)
            or not account[key].strip()
            or any(ord(char) < 32 for char in account[key])
        ):
            raise ValueError("Missing or invalid mailbox field: " + key)
    _authenticationValidate(account)
    if account["role"] not in ROLES:
        raise ValueError("Unknown mailbox role")
    if account["id"] in identifiers:
        raise ValueError("Duplicate mailbox ID")
    identifiers.add(account["id"])
    _portValidate(account.setdefault("port", 993))
    role = account["role"]
    if role in ("shared", "support") and any(
        key in account
        for key in (
            "localArchive",
            "migrationTarget",
            "folderMappings",
            "archiveFormat",
        )
    ):
        raise ValueError(
            "Shared/support mailboxes cannot declare personal archive settings"
        )
    if role == "personal" and not account.get("localArchive"):
        raise ValueError("Personal mailbox requires localArchive")
    if "localArchive" in account:
        _archiveValidate(account, base)
    if account.get("archiveFormat", "thunderbird") not in ("thunderbird", "maildir"):
        raise ValueError("archiveFormat must be thunderbird or maildir")
    _mappingsValidate(account.get("folderMappings", {}))
    if role != "legacy" and "migrationTarget" in account:
        raise ValueError("Only legacy mailboxes may declare migrationTarget")


def _archiveValidate(account: dict, base: Path) -> None:
    value = account["localArchive"]
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(ord(char) < 32 for char in value)
    ):
        raise ValueError("Invalid localArchive")
    path = Path(value).expanduser()
    account["localArchive"] = str(
        (base / path).absolute() if not path.is_absolute() else path.absolute()
    )


def _authenticationValidate(account: dict) -> None:
    if not any(key in account for key in ("credentialId", "passwordEnv")):
        raise ValueError("Configure credentialId or passwordEnv")
    for key in ("credentialId", "passwordEnv"):
        if key in account and (
            not isinstance(account[key], str)
            or not account[key].strip()
            or any(ord(char) < 32 for char in account[key])
        ):
            raise ValueError("Invalid authentication reference")
    if "password" in account:
        raise ValueError(
            "Plaintext passwords are not accepted in mailbox configuration"
        )


def _legacyValidate(account: dict, indexed: dict) -> None:
    identity = account.get("migrationTarget")
    if not isinstance(identity, str):
        raise ValueError("Legacy migrationTarget must identify a personal mailbox")
    target = indexed.get(identity)
    if not target or target["role"] != "personal":
        raise ValueError("Legacy migrationTarget must identify a personal mailbox")
    if (
        account.get("localArchive")
        and account["localArchive"] != target["localArchive"]
    ):
        raise ValueError("Legacy archive must match its personal target")
    account["localArchive"] = target["localArchive"]


def _mappingsValidate(mappings: dict) -> None:
    if not isinstance(mappings, dict):
        raise ValueError("folderMappings must be an object")
    for key, value in mappings.items():
        if (
            not isinstance(key, str)
            or not key
            or not isinstance(value, str)
            or not value
        ):
            raise ValueError(
                "folderMappings must map server paths to canonical folder paths"
            )
        if any(part in ("", ".", "..") for part in value.split("/")) or any(
            ord(char) < 32 for char in key + value
        ):
            raise ValueError("folderMappings must use safe canonical folder paths")


def _portValidate(port: int) -> None:
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid IMAP port")
