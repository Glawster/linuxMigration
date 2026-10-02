"""Packaged CLI entry point."""

import argparse
import json
from pathlib import Path
import tomllib
from typing import Any

from organiseMyProjects.logUtils import getLogger, setApplication

## workflow


def main() -> None:
    """Read configuration, run audit, optionally save, then display results."""
    parser = parserBuild()
    args = parser.parse_args()
    setApplication("mailAgent")
    logger = getLogger(includeConsole=not args.json, dryRun=not args.confirm)
    try:
        from mailAgent.configuration import configValidate

        path = args.config.expanduser().absolute()
        config = configValidate(tomllib.loads(path.read_text()), path.parent)
        if not args.json:
            from mailAgent.auditUi import auditShow
        snapshot = _snapshotBuild(args, config, logger)
        if args.json:
            print(json.dumps(snapshot, indent=2))
        else:
            auditShow(snapshot)
            print(f'Audit complete: {len(snapshot["mailboxes"])} mailboxes')
        if any(
            mailbox.get("failed")
            or not mailbox.get("inventory", {}).get("complete", True)
            for mailbox in snapshot["mailboxes"]
        ):
            raise SystemExit(1)
    except (OSError, ValueError, KeyError):
        parser.exit(
            1,
            "Audit failed: check configuration (including roles) and snapshot files\n",
        )


## arguments


def parserBuild() -> argparse.ArgumentParser:
    """Define read-only audit and planning options."""
    parser = argparse.ArgumentParser(
        description="Read-only mailbox audit and archive/migration planning"
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
        help="persist audit and plan snapshot (never changes mail)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print JSON instead of opening the audit TUI",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="inspect Date headers and build archive/migration proposals; execution disabled",
    )
    return parser


## utilities


def _snapshotBuild(args: argparse.Namespace, config: dict, logger: Any) -> dict:
    from mailAgent.discovery import discoveryRun, snapshotCompare, snapshotSave

    options = {"includeMessages": args.plan}
    if config["general"].get("credentialsFile"):
        options["credentialsFile"] = Path(config["general"]["credentialsFile"])
    snapshot = discoveryRun(
        config["mailboxes"], args.thunderbird.expanduser(), **options
    )
    if args.plan:
        from mailAgent.migrationPlanning import migrationPlan

        snapshot["migrationPlan"] = migrationPlan(config, snapshot)
    state = args.state.expanduser()
    if args.confirm:
        logger.action("persist discovery snapshot")
        snapshotSave(snapshot, state)
        logger.done("persist discovery snapshot")
    else:
        previous = (
            json.loads((state / "latest.json").read_text())
            if (state / "latest.json").is_file()
            else {}
        )
        if previous and previous.get("schemaVersion") != 1:
            raise ValueError("Unsupported previous snapshot schema")
        snapshot["changes"] = snapshotCompare(previous, snapshot)
    return snapshot
