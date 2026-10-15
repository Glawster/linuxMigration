"""Server capability compatibility probes for explicit IMAP execution."""

from collections.abc import Callable
from typing import Any

from mailAgent.imapExecution import ImapExecutionBlocked, imapFileExecute as _imapFileExecute

_MAX_UID = "4294967295"


def exactExpungeRun(client: Any, operation: Callable[[], dict]) -> dict:
    """Run an operation only when exact UID EXPUNGE support is verified.

    Some servers accept UID EXPUNGE but fail to advertise UIDPLUS. Probe the
    exact command against the maximum impossible current UID while INBOX is
    read-only, then expose UIDPLUS only for the duration of the operation.
    """
    capabilities = tuple(client.capabilities)
    advertised = {
        value.decode().upper() if isinstance(value, bytes) else str(value).upper()
        for value in capabilities
    }
    if "UIDPLUS" in advertised:
        return operation()

    status, _ = client.select('"INBOX"', readonly=True)
    if status != "OK":
        raise ImapExecutionBlocked("unsupported")
    _, uidNextRows = client.response("UIDNEXT")
    if (
        not uidNextRows
        or len(uidNextRows) != 1
        or not isinstance(uidNextRows[0], bytes)
        or not uidNextRows[0].isdigit()
        or int(uidNextRows[0]) >= int(_MAX_UID)
    ):
        raise ImapExecutionBlocked("unsupported")
    try:
        status, _ = client.uid("EXPUNGE", _MAX_UID)
    except Exception as error:
        raise ImapExecutionBlocked("unsupported") from error
    if status != "OK":
        raise ImapExecutionBlocked("unsupported")

    client.capabilities = capabilities + (b"UIDPLUS",)
    try:
        return operation()
    finally:
        client.capabilities = capabilities


def imapFileExecute(client, approved, config, currentObserve, actionId, **kwargs):
    """Run the existing executor with verified exact UID EXPUNGE compatibility."""
    return exactExpungeRun(
        client,
        lambda: _imapFileExecute(
            client, approved, config, currentObserve, actionId, **kwargs
        ),
    )
