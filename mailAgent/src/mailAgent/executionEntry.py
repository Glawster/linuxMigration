"""Execution entry point with narrowly scoped IMAP compatibility handling."""

import mailAgent.executionApp as executionApp
from mailAgent.executionCli import main as loggedMain
from mailAgent.executionCompat import imapFileExecute


def main() -> None:
    """Run the logged execution TUI with verified exact-expunge compatibility."""
    executionApp.imapFileExecute = imapFileExecute
    loggedMain()
