"""Bounded retry for transient IMAP session loss during mail execution."""

import imaplib
from typing import Callable, TypeVar

_Result = TypeVar("_Result")


def executionWithReconnect(
    operation: Callable[[], _Result], logger=None
) -> _Result:
    """Retry one operation once when the IMAP server aborts the session.

    Only ``imaplib.IMAP4.abort`` is retried. Policy, validation and other
    execution failures propagate immediately. The operation owns its IMAP
    connection, so a retry necessarily reconnects, logs in and revalidates the
    action from current observations.
    """
    try:
        return operation()
    except imaplib.IMAP4.abort:
        if logger is not None:
            logger.warning(
                "Moving Mail IMAP connection closed by server; "
                "reconnecting and retrying once"
            )

    try:
        return operation()
    except imaplib.IMAP4.abort as error:
        raise RuntimeError("IMAP connection closed by server after retry") from error
