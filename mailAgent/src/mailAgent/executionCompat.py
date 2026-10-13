"""Server capability compatibility probes for explicit IMAP execution."""

from mailAgent.imapExecution import ImapExecutionBlocked, imapFileExecute as _imapFileExecute

_MAX_UID = "4294967295"


def imapFileExecute(client, approved, config, currentObserve, actionId, **kwargs):
    """Run the existing executor after safely verifying exact UID EXPUNGE support.

    Some servers accept UID EXPUNGE but fail to advertise UIDPLUS. The core
    executor deliberately requires UIDPLUS because it must never use global
    EXPUNGE. For such servers, probe the exact command against the maximum UID
    while INBOX is read-only; only then expose UIDPLUS to the unchanged core
    executor for this connection.
    """
    capabilities = tuple(client.capabilities)
    advertised = {
        value.decode().upper() if isinstance(value, bytes) else str(value).upper()
        for value in capabilities
    }
    if "UIDPLUS" in advertised:
        return _imapFileExecute(
            client, approved, config, currentObserve, actionId, **kwargs
        )

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
        return _imapFileExecute(
            client, approved, config, currentObserve, actionId, **kwargs
        )
    finally:
        client.capabilities = capabilities
