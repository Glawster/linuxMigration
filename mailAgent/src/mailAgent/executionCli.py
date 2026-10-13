"""Logging entry point for the explicit mailbox execution TUI."""

import asyncio
import imaplib
from pathlib import Path
import tomllib

from organiseMyProjects.logUtils import getLogger, setApplication
from textual.widgets import Button, Static

from mailAgent.configuration import configValidate
from mailAgent.executionApp import (
    ExecutionApp,
    executionRunOne,
    filingPlanFresh,
    parserBuild,
    thunderbirdRoot,
)
from mailAgent.executionReview import executionReviewBuild
from mailAgent.version import applicationVersion


class LoggedExecutionApp(ExecutionApp):
    """Execution TUI that persists concise, secret-free operation outcomes."""

    TITLE = f"mailAgent Execute · {applicationVersion()}"

    def __init__(self, review: dict, reviewRefresh, execute, logger) -> None:
        super().__init__(review, reviewRefresh, execute)
        self.logger = logger

    async def workerRun(self, operation, executed: bool) -> None:
        """Run one operation and persist its user-visible outcome to the log."""
        status = self.query_one("#execution-status", Static)
        try:
            result = await asyncio.to_thread(operation)
            refreshed = await asyncio.to_thread(self.reviewRefresh)
            self.review = refreshed
            self.reviewShow()
            if executed:
                state = (
                    result.get("state", "unknown")
                    if isinstance(result, dict)
                    else "unknown"
                )
                message = f"Execution finished: {state}. Review refreshed."
                self.logger.info(message)
            else:
                message = "Execution review refreshed."
                self.logger.info(message)
            status.update(message)
        except Exception as error:
            message = f"Execution blocked or failed: {error}"
            self.logger.error(message)
            status.update(message)
        finally:
            self.query_one("#execution-refresh", Button).disabled = False
            self.query_one("#execution-run", Button).disabled = not bool(
                self.review.get("candidates")
            )


def main() -> None:
    """Open execution mode with durable logging of review and execution failures."""
    parser = parserBuild()
    args = parser.parse_args()
    setApplication("mailAgent")
    logger = getLogger(includeConsole=False)
    path = args.config.expanduser().absolute()
    try:
        config = configValidate(tomllib.loads(path.read_text()), path.parent)
        thunderbird = thunderbirdRoot(args.thunderbird)
        filingPlan = filingPlanFresh(config, thunderbird)
        review = executionReviewBuild(filingPlan, config)
    except (OSError, ValueError, KeyError) as error:
        message = f"Execution review failed: {error}"
        logger.error(message)
        parser.exit(1, message + "\n")

    def reviewRefresh() -> dict:
        return executionReviewBuild(filingPlanFresh(config, thunderbird), config)

    def execute(actionId: str, selectedReview: dict) -> dict:
        logger.info(f"Execution requested: {actionId[:12]}")
        return executionRunOne(
            actionId,
            selectedReview,
            config,
            thunderbird,
            clientFactory=imaplib.IMAP4_SSL,
        )

    logger.info(
        f"Execution review ready: {len(review.get('candidates', []))} candidates, "
        f"{len(review.get('blocked', []))} blocked"
    )
    LoggedExecutionApp(review, reviewRefresh, execute, logger).run()
