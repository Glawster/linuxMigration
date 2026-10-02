"""GPG-backed credentials, decrypted only into memory and never logged."""

import json
import os
import stat
import subprocess
from pathlib import Path


class CredentialError(ValueError):
    """A deliberately secret-free credential failure safe for user display."""


## credentials


def credentialGet(account: dict, store: Path | None = None) -> str:
    """Resolve an encrypted credential, or the legacy environment source."""
    if "credentialId" in account:
        identity = account["credentialId"]
        if not isinstance(identity, str) or not identity.strip():
            raise CredentialError("Invalid credentialId")
        credentials = credentialsLoad(store)
        try:
            if identity not in credentials:
                raise CredentialError("Credential ID not found in encrypted store")
            return credentials[identity]["password"]
        finally:
            credentials.clear()
    name = account.get("passwordEnv")
    if not isinstance(name, str) or not name.strip():
        raise CredentialError("Configure credentialId or passwordEnv")
    password = os.environ.get(name)
    if not password or not password.strip():
        raise CredentialError("Password environment variable is missing or empty")
    return password


def credentialsDecrypt(path: Path) -> bytes:
    """Validate the encrypted file and capture GPG plaintext in memory."""
    path = _storeValidate(path)
    try:
        result = subprocess.run(
            ["gpg", "--batch", "--decrypt", "--", str(path)],
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )
    except FileNotFoundError:
        raise CredentialError(
            "GPG executable is missing; install GPG before running"
        ) from None
    except subprocess.TimeoutExpired:
        raise CredentialError("GPG decryption timed out") from None
    except OSError:
        raise CredentialError("Unable to run GPG") from None
    if result.returncode != 0:
        raise CredentialError(
            "GPG decryption failed; verify the store and GPG unlock setup"
        )
    return result.stdout


def credentialsLoad(path: Path | None = None) -> dict:
    """Parse and validate decrypted JSON without creating a plaintext file."""
    plaintext = credentialsDecrypt(
        path
        if path is not None
        else Path.home() / ".config/mailAgent/credentials.json.gpg"
    )
    try:
        try:
            credentials = json.loads(plaintext, object_pairs_hook=_objectParse)
        except (ValueError, UnicodeError, RecursionError):
            raise CredentialError(
                "Decrypted credential store is not valid JSON"
            ) from None
        credentialsValidate(credentials)
        return credentials
    finally:
        del plaintext


def credentialsValidate(credentials: dict) -> None:
    """Require credential objects with nonempty password strings."""
    if not isinstance(credentials, dict):
        raise CredentialError("Credential store must contain a JSON object")
    for identity, entry in credentials.items():
        if (
            not isinstance(identity, str)
            or not identity.strip()
            or not isinstance(entry, dict)
        ):
            raise CredentialError("Credential store contains an invalid entry")
        password = entry.get("password")
        if not isinstance(password, str) or not password.strip():
            raise CredentialError(
                "Credential entry requires a nonempty password string"
            )


## utilities


def _objectParse(pairs: list[tuple]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _storeValidate(path: Path) -> Path:
    path = Path(path).expanduser().absolute()
    if path.suffix != ".gpg":
        raise CredentialError("Credential store must be an encrypted .gpg file")
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        raise CredentialError("Encrypted credential store is missing") from None
    except OSError:
        raise CredentialError("Cannot inspect encrypted credential store") from None
    if not stat.S_ISREG(metadata.st_mode):
        raise CredentialError(
            "Encrypted credential store must be a regular file, not a symlink"
        )
    if metadata.st_mode & 0o077:
        raise CredentialError("Unsafe credential store permissions; use chmod 600")
    try:
        resolved = path.resolve(strict=True)
        if any((parent / ".git").exists() for parent in resolved.parents):
            raise CredentialError(
                "Encrypted credential store must remain outside a repository"
            )
    except OSError:
        raise CredentialError("Cannot inspect encrypted credential store") from None
    return resolved
