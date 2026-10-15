"""Bounded retry behaviour for transient IMAP session loss."""

import imaplib

import pytest

from mailAgent.executionRetry import executionWithReconnect


class _Logger:
    def __init__(self) -> None:
        self.warnings = []

    def warning(self, message: str) -> None:
        self.warnings.append(message)


def testExecutionRetriesOneImapAbort() -> None:
    calls = []
    logger = _Logger()

    def operation() -> dict:
        calls.append(True)
        if len(calls) == 1:
            raise imaplib.IMAP4.abort("command: EXAMINE => Server shutting down.")
        return {"state": "completed"}

    assert executionWithReconnect(operation, logger) == {"state": "completed"}
    assert len(calls) == 2
    assert logger.warnings == [
        "Moving Mail IMAP connection closed by server; reconnecting and retrying once"
    ]


def testExecutionReportsSecondImapAbortClearly() -> None:
    calls = []

    def operation() -> None:
        calls.append(True)
        raise imaplib.IMAP4.abort("command: EXAMINE => Server shutting down.")

    with pytest.raises(
        RuntimeError, match="IMAP connection closed by server after retry"
    ):
        executionWithReconnect(operation)

    assert len(calls) == 2


def testExecutionDoesNotRetryValidationFailure() -> None:
    calls = []

    def operation() -> None:
        calls.append(True)
        raise ValueError("stale-source")

    with pytest.raises(ValueError, match="stale-source"):
        executionWithReconnect(operation)

    assert len(calls) == 1
