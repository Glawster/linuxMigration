"""Packaged CLI entry point."""

import argparse
import json
from pathlib import Path
import tomllib

from organiseMyProjects.logUtils import getLogger, setApplication


## workflow


def main() -> None:
    """Read configuration, run audit, optionally save, then display results."""
    parser = argparse.ArgumentParser(
        description="Read-only mailbox and Thunderbird audit"
    )
    parser.add_argument(
        "--config", type=Path, default=Path.home() / ".config/mailAgent/config.toml"
    )
    parser.add_argument(
        "--thunderbird", type=Path, default=Path.home() / ".thunderbird"
    )
    parser.add_argument(
        "--state", type=Path, default=Path.home() / ".local/state/mailAgent/discovery"
    )
    parser.add_argument(
        "--confirm",
        "-y",
        action="store_true",
        help="persist discovery snapshot (never changes mail)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print JSON instead of opening the audit TUI",
    )
    args = parser.parse_args()
    setApplication("mailAgent")
    logger = getLogger(includeConsole=not args.json, dryRun=not args.confirm)
    from mailAgent.discovery import discoveryRun, snapshotCompare, snapshotSave

    try:
        config = tomllib.loads(args.config.read_text())
        accounts = config["mailboxes"]
        identifiers = set()
        for account in accounts:
            for key in ("id", "name", "host", "username", "passwordEnv"):
                if not isinstance(account.get(key), str) or not account[key]:
                    raise ValueError("Invalid mailbox configuration")
            if account["id"] in identifiers:
                raise ValueError("Duplicate mailbox ID")
            identifiers.add(account["id"])
        if not args.json:
            from mailAgent.auditUi import auditShow
        snapshot = discoveryRun(accounts, args.thunderbird)
        if args.confirm:
            logger.action("persist discovery snapshot")
            snapshotSave(snapshot, args.state)
            logger.done("persist discovery snapshot")
        else:
            previous = (
                json.loads((args.state / "latest.json").read_text())
                if (args.state / "latest.json").is_file()
                else {}
            )
            snapshot["changes"] = snapshotCompare(previous, snapshot)
        if args.json:
            print(json.dumps(snapshot, indent=2))
        else:
            auditShow(snapshot)
            print(f'Audit complete: {len(snapshot["mailboxes"])} mailboxes')
        if any(mailbox.get("failed") for mailbox in snapshot["mailboxes"]):
            raise SystemExit(1)
    except (OSError, ValueError, KeyError):
        parser.exit(1, "Audit failed: check configuration and snapshot files\n")
