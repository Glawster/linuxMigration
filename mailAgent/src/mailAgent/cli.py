"""Packaged CLI entry point."""

import argparse
from datetime import datetime, timezone
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
    logger = getLogger(includeConsole=True, dryRun=not args.confirm)
    try:
        from mailAgent.configuration import configValidate

        path = args.config.expanduser().absolute()
        rawConfig = tomllib.loads(path.read_text())
        try:
            config = configValidate(rawConfig, path.parent)
        except ValueError as error:
            parser.exit(1, f"Audit failed: configuration: {error}\n")
        if args.json is None:
            from mailAgent.auditUi import auditShow
        snapshot = _snapshotBuild(args, config, logger)
        if args.plan:
            from mailAgent.planSummary import planSummaryShow

            planSummaryShow(snapshot["migrationPlan"], logger)
        if args.json is None:
            snapshot = _interactiveShow(args, config, snapshot, logger)
            logger.info("Audit complete: %d mailboxes", len(snapshot["mailboxes"]))
        if args.json is not None:
            output = _jsonPath(args)
            _jsonWrite(snapshot, output)
            logger.value("JSON output", output)
        failed = [
            mailbox
            for mailbox in snapshot["mailboxes"]
            if mailbox.get("failed")
            or not mailbox.get("inventory", {}).get("complete", True)
        ]
        if failed:
            for mailbox in failed:
                for issue in mailbox.get("issues", []):
                    logger.error(issue)
                for issue in mailbox.get("inventory", {}).get("issues", []):
                    logger.error(issue.get("message", "Mailbox inventory incomplete"))
            raise SystemExit(1)
    except (OSError, ValueError, KeyError):
        parser.exit(
            1,
            "Audit failed: check configuration (including roles) and snapshot files\n",
        )


def _interactiveShow(
    args: argparse.Namespace,
    config: dict,
    snapshot: dict,
    logger: Any,
) -> dict:
    """Run the TUI and execute requested read-only follow-up workflows."""
    from mailAgent.auditUi import auditShow
    from mailAgent.planSummary import planSummaryShow

    while auditShow(snapshot) == "runPlanning":
        planningArgs = argparse.Namespace(**vars(args))
        planningArgs.plan = True
        planningArgs.confirm = False
        planningArgs.json = None
        snapshot = _snapshotBuild(planningArgs, config, logger)
        planSummaryShow(snapshot["migrationPlan"], logger)
    return snapshot


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
        nargs="?",
        const="",
        metavar="FILE",
        help=(
            "write JSON to FILE instead of stdout; when FILE is omitted use "
            "<state>/plan.json or <state>/audit.json"
        ),
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

    options = {
        "includeMessages": args.plan,
        "includeInbox": args.json is None,
    }
    if config["general"].get("credentialsFile"):
        options["credentialsFile"] = Path(config["general"]["credentialsFile"])
    snapshot = discoveryRun(
        config["mailboxes"], _thunderbirdRoot(args.thunderbird), **options
    )
    snapshot["localArchives"] = _localArchivesDiscover(config)
    state = args.state.expanduser()
    if args.plan:
        from mailAgent.migrationPlanning import migrationPlan

        snapshot["migrationPlan"] = migrationPlan(config, snapshot)
        snapshot["migrationPlan"]["generatedAt"] = datetime.now(timezone.utc).isoformat()
        _planSave(snapshot["migrationPlan"], state)
    elif args.json is None:
        storedPlan = _planLoad(state)
        if storedPlan is not None:
            snapshot["migrationPlan"] = storedPlan
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


def _jsonPath(args: argparse.Namespace) -> Path:
    """Resolve explicit or default JSON output path."""
    if args.json is None:
        raise ValueError("JSON output was not requested")
    if args.json == "":
        name = "plan.json" if args.plan else "audit.json"
        return args.state.expanduser() / name
    return Path(args.json).expanduser()


def _jsonWrite(snapshot: dict, path: Path) -> None:
    """Write machine-readable output atomically without using stdout."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(snapshot, indent=2) + "\n")
    temporary.replace(path)



def _thunderbirdRoot(configured: Path) -> Path:
    """Resolve native or Flatpak Thunderbird metadata root."""
    configured = configured.expanduser()
    if (configured / "profiles.ini").is_file():
        return configured
    if configured == Path.home() / ".thunderbird":
        for candidate in (
            Path.home()
            / ".var/app/org.mozilla.thunderbird_esr/.thunderbird",
            Path.home()
            / ".var/app/org.mozilla.Thunderbird/.thunderbird",
        ):
            if (candidate / "profiles.ini").is_file():
                return candidate
    return configured



def _localArchivesDiscover(config: dict) -> list[dict]:
    """Discover configured personal local archive folders for audit display."""
    from mailAgent.archiveDiscovery import archiveDiscover

    archives = []
    for account in config["mailboxes"]:
        if account.get("role") != "personal":
            continue
        root = account.get("localArchive")
        if not root:
            continue
        archive = archiveDiscover(Path(root))
        archives.append(
            dict(
                mailbox=account["id"],
                name=Path(root).name,
                root=root,
                format=archive["format"],
                available=archive["available"],
                complete=archive.get("complete", True),
                folders=archive.get("folders", []),
                issues=archive.get("issues", []),
            )
        )
    return archives



def _planPath(state: Path) -> Path:
    """Return the durable latest-plan path."""
    return state.expanduser() / "latest-plan.json"


def _planSave(plan: dict, state: Path) -> Path:
    """Persist the latest read-only plan atomically."""
    path = _planPath(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(plan, indent=2) + "\n")
    temporary.replace(path)
    return path


def _planLoad(state: Path) -> dict | None:
    """Load the latest stored plan when available."""
    path = _planPath(state)
    if not path.is_file():
        return None
    plan = json.loads(path.read_text())
    if not isinstance(plan, dict) or plan.get("schemaVersion") != 1:
        raise ValueError("Unsupported stored migration plan schema")
    return plan
