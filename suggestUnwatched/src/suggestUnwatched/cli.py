"""Suggest the oldest unwatched video folders under a directory."""

from __future__ import annotations

import argparse
import importlib.util
import logging
from pathlib import Path
import sqlite3
import sys

from organiseMyProjects.logUtils import drawBox, getLogger, setApplication

from suggestUnwatched.config import configDefaultPath, configLoad
from suggestUnwatched.folders import (
    VideoFolder,
    folderExempt,
    foldersScan,
    foldersSelect,
    sizeFormat,
)
from suggestUnwatched.plex import DEFAULT_PLEX_DB, watchLoad
from suggestUnwatched.removal import removalScriptPath, removalScriptWrite

## workflow


def main() -> None:
    """Scan a directory and print the oldest unwatched video folders."""
    parser = parserBuild()
    args = parser.parse_args()
    setApplication("suggestUnwatched")
    logger = getLogger(includeConsole=True, dryRun=False)
    logger.value("version", repoVersionRead())
    try:
        root, database, count, config, exemptShows = _argumentsRead(args)
        _exemptLog(config, exemptShows, logger)
        selected, folders = _scanRun(root, database, count, exemptShows, logger)
    except ValueError as error:
        logger.error(str(error))
        raise SystemExit(1) from None
    if _chooserRequested(args):
        _chooseRun(root, folders, exemptShows, count, config, logger)
        return
    reportShow(selected, folders, root, logger)


def repoVersionRead(repoRoot: Path | None = None) -> str:
    """Return the linuxMigration repository version this tool runs from.

    Uses the repository's repoVersion.py (git describe against release tags,
    falling back to VERSION); "unknown" when the tool is not in the repository.
    """
    root = repoRoot or Path(__file__).resolve().parents[3]
    helper = root / "repoVersion.py"
    if not helper.is_file():
        return "unknown"
    spec = importlib.util.spec_from_file_location("repoVersion", helper)
    if spec is None or spec.loader is None:
        return "unknown"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.repoVersion(root)


def parserBuild() -> argparse.ArgumentParser:
    """Build the suggestion command line."""
    parser = argparse.ArgumentParser(
        description=(
            "Suggest unwatched video folders. In a terminal, mark shows exempt "
            "and the next oldest folder fills in. --report only prints. "
            "Nothing is moved or deleted."
        )
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="print suggestions and exit without opening the chooser",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="how many folders to suggest (default: 5)",
    )
    parser.add_argument(
        "--plex-db",
        type=Path,
        default=DEFAULT_PLEX_DB,
        help="Plex library SQLite database",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=("JSON exempt list " f"(default: {configDefaultPath()})"),
    )
    return parser


def reportShow(selected, folders, root: Path, logger) -> None:
    """Log the suggestion summary and the chosen folders."""
    unwatched = sum(folder.watchedCount == 0 for folder in folders)
    logger.value("video folders", len(folders))
    logger.value("unwatched folders", unwatched)
    logger.value("suggested", len(selected))
    if not selected:
        logger.info("no unwatched video folders to suggest")
        logger.done("suggestion complete")
        return
    lines = [
        _reportLine(index, folder, root) for index, folder in enumerate(selected, 1)
    ]
    drawBox("\n".join(lines), logger=logger)
    logger.done("suggestion complete")


## arguments


def countRequire(count: int) -> int:
    """Reject a suggestion count below one."""
    if count < 1:
        raise ValueError("Count must be at least 1.")
    return count


def pathOptionalFile(path: Path) -> Path:
    """Return an absolute path. A missing file is left for the caller."""
    resolved = path.expanduser().absolute()
    if resolved.exists() and not resolved.is_file():
        raise ValueError(f"Exempt list is not a file: {resolved}")
    return resolved


def pathRequireDirectory(path: Path) -> Path:
    """Return an absolute directory path or raise ValueError."""
    resolved = path.expanduser().absolute()
    if not resolved.is_dir():
        raise ValueError(f"Scan root is not a directory: {resolved}")
    return resolved


def pathRequireFile(path: Path) -> Path:
    """Return an absolute file path or raise ValueError."""
    resolved = path.expanduser().absolute()
    if not resolved.is_file():
        raise ValueError(f"Plex database is not a file: {resolved}")
    return resolved


def _argumentsRead(
    args: argparse.Namespace,
) -> tuple[Path, Path, int, Path, list[str]]:
    config = pathOptionalFile(args.config or configDefaultPath())
    return (
        pathRequireDirectory(Path(args.root)),
        pathRequireFile(args.plex_db),
        countRequire(args.count),
        config,
        configLoad(config),
    )


def _exemptLog(config: Path, exemptShows: list[str], logger) -> None:
    if config.is_file():
        logger.value("exempt list", config)
    else:
        logger.info("no exempt list")
    logger.value("exempt shows", len(exemptShows))


## report


def _relative(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def _reportLine(index: int, folder: VideoFolder, root: Path) -> str:
    when = folder.airDate.isoformat() if folder.airDate else "unknown"
    source = folder.airDateSource or "none"
    return (
        f"{index}. {_relative(folder.path, root)} | {when} ({source}) | "
        f"{_sizeFormat(folder.sizeBytes)} | "
        f"{folder.videoCount} videos, {folder.plexCount} in plex"
    )


def _scanRun(
    root: Path,
    database: Path,
    count: int,
    exemptShows: list[str],
    logger,
):
    logger.doing("scanning video folders")
    logger.value("root", root)
    try:
        records = watchLoad(database, root)
        found = foldersScan(root, records)
    except OSError as error:
        raise ValueError(f"Cannot scan video folders: {error}") from error
    except sqlite3.Error as error:
        raise ValueError(f"Cannot read the Plex library: {error}") from error
    skipped = sum(folderExempt(folder, root, exemptShows) for folder in found)
    logger.value("plex videos", len(records))
    logger.value("exempt folders", skipped)
    logger.done("scanning video folders")
    return foldersSelect(found, count, root, exemptShows), found


def _sizeFormat(sizeBytes: int) -> str:
    return sizeFormat(sizeBytes)


## chooser


def _chooseRun(root, folders, exemptShows, count, config, logger) -> None:
    from suggestUnwatched.suggestView import SuggestApp

    logger.info("opening suggestion chooser")
    handlers = _consoleQuiet(logger)
    app = SuggestApp(root, folders, exemptShows, count, config)
    try:
        app.run()
    finally:
        _consoleRestore(logger, handlers)
    selected = foldersSelect(folders, count, root, app.exemptShows)
    logger.info("shows that could be archived or deleted")
    reportShow(selected, folders, root, logger)
    script = removalScriptWrite(removalScriptPath(), selected)
    logger.value("remove script", script)
    logger.info("review the script before running it")


def _chooserRequested(args: argparse.Namespace) -> bool:
    if args.report:
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


def _consoleQuiet(logger) -> list[logging.Handler]:
    handlers = [
        handler
        for handler in logger.logger.handlers
        if type(handler) is logging.StreamHandler
    ]
    for handler in handlers:
        logger.logger.removeHandler(handler)
    return handlers


def _consoleRestore(logger, handlers: list[logging.Handler]) -> None:
    attached = set(logger.logger.handlers)
    for handler in handlers:
        if handler not in attached:
            logger.logger.addHandler(handler)
