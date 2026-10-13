"""Mailbox credentials in the Linux PAM login-session keyring, never on disk."""

from hashlib import sha256
import os
from pathlib import Path
import subprocess


class SessionCredentialError(ValueError):
    """Fixed secret-free session-cache failure safe for user display."""


## session


def credentialsSessionGet(identity: str) -> bytes | None:
    """Read a cached payload from the inherited login keyring."""
    _sessionValidate()
    key = _keyFind(identity)
    if key is None:
        return None
    result = _commandRun(["pipe", key])
    if result.returncode:
        raise SessionCredentialError("Cannot read login-session password cache")
    return result.stdout


def credentialsSessionIdentity(path: Path) -> str:
    """Bind cache reuse to the validated path and encrypted file contents."""
    try:
        digest = sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise SessionCredentialError(
            "Cannot inspect encrypted store for session cache"
        ) from None
    return (
        "mailAgent:credentials:v1:"
        + sha256((str(path) + "\0" + digest).encode()).hexdigest()
    )


def credentialsSessionPut(identity: str, payload: bytes) -> None:
    """Cache validated password JSON using stdin and session-only possession."""
    _sessionValidate()
    result = _commandRun(["padd", "user", identity, "@s"], payload)
    if result.returncode or not result.stdout.strip().isdigit():
        raise SessionCredentialError("Cannot store login-session password cache")
    key = result.stdout.strip().decode("ascii")
    # Possessor permissions only: other login sessions cannot read by key ID.
    permissions = _commandRun(["setperm", key, "0x3f000000"])
    if permissions.returncode:
        _commandRun(["revoke", key])
        raise SessionCredentialError("Cannot protect login-session password cache")


## utilities


def _commandRun(
    arguments: list[str], payload: bytes | None = None
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["keyctl", *arguments],
            input=payload,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise SessionCredentialError(
            "Login-session password cache requires working keyctl (keyutils)"
        ) from None


def _keyFind(identity: str) -> str | None:
    result = _commandRun(["search", "@s", "user", identity])
    if result.returncode:
        return None
    key = result.stdout.strip()
    if not key.isdigit():
        raise SessionCredentialError("Invalid login-session password cache identity")
    return key.decode("ascii")


def _sessionValidate() -> None:
    result = _commandRun(["rdescribe", "@s"])
    fields = result.stdout.strip().split(b";", 4)
    if (
        result.returncode
        or len(fields) != 5
        or fields[0] != b"keyring"
        or fields[1] != str(os.getuid()).encode()
        or fields[4] != b"_ses"
    ):
        raise SessionCredentialError(
            "Password cache requires a PAM login-session keyring revoked at logout; "
            "disable credentialsSessionCache for this launch context"
        )
