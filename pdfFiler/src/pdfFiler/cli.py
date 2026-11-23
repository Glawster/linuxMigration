"""pdfFiler command line.

  pdfFiler [inbox file] [-y|--confirm] [--root DIR] [--inbox DIR]
  pdfFiler suggest PDF... [--root DIR]
  pdfFiler index show [--root DIR]

With no subcommand it runs `inbox file`. `--confirm` is the default:
files move, and Skip in the window leaves a PDF in the inbox.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import shutil
import sys
from pathlib import Path

from organiseMyProjects.logUtils import getLogger, line, runStart, setApplication

from pdfFiler import APPLICATION
from pdfFiler.cabinet import cabinetIndexBuild
from pdfFiler.learned import learnedDefaultPath, learnedLoad
from pdfFiler.rules import configDefaultPath, rulesLoad
from pdfFiler.suggest import suggestionMake
from pdfFiler.text import textOfPdf

_COMMANDS = {"inbox", "suggest", "index"}
_REQUIRED_TOOLS = ("pdftotext", "pdftoppm", "pdfinfo", "gio")

## workflow


def main(argv: list[str] | None = None) -> int:
    """Run a pdfFiler command; returns the exit status."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or (
        arguments[0] not in _COMMANDS and arguments[0] not in ("-h", "--help", "--version")
    ):
        arguments = ["inbox", "file", *arguments]
    parser = parserBuild()
    args = parser.parse_args(arguments)
    if args.version:
        print(f"{APPLICATION} {repoVersionRead()}")
        return 0
    if not getattr(args, "handler", None):
        parser.print_help()
        return 2

    setApplication(APPLICATION)
    # Filing moves files. --confirm is the default, so the logger never
    # marks actions as a preview. suggest and index show still change nothing.
    logger = getLogger(includeConsole=True, dryRun=False)
    try:
        return args.handler(args, logger)
    except ValueError as error:
        logger.error(str(error))
        return 1


def parserBuild() -> argparse.ArgumentParser:
    """Build the command line: inbox file, suggest and index show."""
    parser = argparse.ArgumentParser(
        prog="pdfFiler",
        description=(
            "File scanned PDFs from the myCabinets Inbox, suggesting the folder, "
            "name, type and date from what is already filed. Files are moved; "
            "--confirm is accepted and is the default. Never overwrites."
        ),
    )
    parser.add_argument("--version", action="store_true", help="show the version")
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    inbox = commands.add_parser("inbox", help="file the inbox")
    inboxActions = inbox.add_subparsers(dest="action", metavar="ACTION", required=True)
    inboxFileParser = inboxActions.add_parser("file", help="offer each inbox PDF and file it")
    _commonOptions(inboxFileParser)
    inboxFileParser.add_argument(
        "--inbox", type=Path, help="folder to file from (default <root>/Inbox)"
    )
    inboxFileParser.add_argument(
        "-y",
        "--confirm",
        action="store_true",
        default=True,
        help="move the files (the default; accepted so existing commands keep working)",
    )
    inboxFileParser.set_defaults(handler=inboxFileCommand)

    suggest = commands.add_parser("suggest", help="show the suggestion for PDFs; changes nothing")
    _commonOptions(suggest)
    suggest.add_argument("pdfs", nargs="+", type=Path, metavar="PDF")
    suggest.set_defaults(handler=suggestCommand)

    index = commands.add_parser("index", help="what pdfFiler has learned")
    indexActions = index.add_subparsers(dest="action", metavar="ACTION", required=True)
    indexShowParser = indexActions.add_parser("show", help="list identifiers, labels and types")
    _commonOptions(indexShowParser)
    indexShowParser.set_defaults(handler=indexShowCommand)
    return parser


def repoVersionRead(repoRoot: Path | None = None) -> str:
    """The linuxMigration version this tool runs from, or "unknown"."""
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


## commands


def indexShowCommand(args: argparse.Namespace, logger) -> int:
    """Print what the index and learned.json hold (criterion 12)."""
    root = _rootValidate(args.root)
    _header(logger, "showing the index", root, args)
    started = dt.datetime.now()
    index = cabinetIndexBuild(root)
    learned = learnedLoad(args.learned)
    seconds = (dt.datetime.now() - started).total_seconds()
    line()
    print("Identifiers")
    for identifier in sorted(index.identifiers):
        folders = ", ".join(str(folder) for folder in index.identifiers[identifier])
        print(f"  {identifier:<24} name     {folders}")
    for identifier, folder in sorted(learned.identifiers.items()):
        print(f"  {identifier:<24} learned  {folder}")
    if learned.conflicts:
        print("Conflicting learned numbers")
        for conflict in learned.conflicts:
            print(f"  {conflict.get('identifier')}: {', '.join(conflict.get('folders', []))}")
    print("Folders")
    for path, info in sorted(index.folders.items()):
        if not info.files:
            continue
        types = ", ".join(f"{name} {count}" for name, count in info.types.most_common(5))
        print(f"  {path}  [{info.files}]  label: {info.labelUsual()}  types: {types or '-'}")
    line()
    logger.value("folders", len(index.folders))
    logger.value("filed pdfs", sum(info.files for info in index.folders.values()))
    logger.value("identifiers", len(index.identifiers) + len(learned.identifiers))
    logger.value("seconds to build", f"{seconds:.2f}")
    logger.done("showing the index")
    return 0


def inboxFileCommand(args: argparse.Namespace, logger) -> int:
    """File the inbox through the filing window (requirement 005)."""
    from pdfFiler.inbox import Options, inboxFile, inboxIndex

    root = _rootValidate(args.root)
    inbox = (args.inbox or root / "Inbox").expanduser()
    if not inbox.is_dir():
        raise ValueError(f"Inbox folder not found: {inbox}")
    missing = [tool for tool in _REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing:
        raise ValueError(
            f"Missing required tools: {', '.join(missing)} (poppler-utils, libglib2.0-bin)"
        )

    _header(logger, "filing inbox pdfs", root, args)
    logger.value("inbox", inbox.resolve())
    logger.value("mode", "confirm")
    line()
    options = Options(
        root=root,
        inbox=inbox.resolve(),
        configPath=args.config,
        learnedPath=args.learned,
    )
    index = inboxIndex(options)
    window = _LazyWindow(index, options.today)
    try:
        counts = inboxFile(options, logger, window, index)
        line()
        logger.value("filed", counts.filed)
        logger.value("already filed, trashed", counts.duplicates)
        logger.value("name taken, left in inbox", counts.conflicts)
        logger.value("skipped", counts.skipped)
        logger.value("numbers learned", counts.learned)
        logger.done("filing inbox pdfs")
        if window.opened and not counts.cancelled:
            window.message(
                "info",
                f"Inbox done: {counts.filed} filed, {counts.duplicates} already filed, "
                f"{counts.conflicts + counts.skipped} left in the inbox.",
            )
    finally:
        window.close()
    return 0


class _LazyWindow:
    """Opens the filing window only when a PDF needs it, so an empty inbox
    or auto-rule filing needs no display."""

    def __init__(self, index, today: dt.date) -> None:
        self._arguments = (index, today)
        self._window = None

    @property
    def opened(self) -> bool:
        return self._window is not None

    def close(self) -> None:
        if self._window is not None:
            self._window.close()

    def decide(self, state, position: int, total: int):
        return self._open().decide(state, position, total)

    def message(self, kind: str, text: str) -> None:
        self._open().message(kind, text)

    def _open(self):
        if self._window is None:
            # The GUI is imported here only: other commands never need it.
            from pdfFiler.ui.filingWindow import FilingWindow

            self._window = FilingWindow(*self._arguments)
        return self._window


def suggestCommand(args: argparse.Namespace, logger) -> int:
    """Print the suggestion for each PDF; nothing moves or is learned."""
    root = _rootValidate(args.root)
    _header(logger, "suggesting", root, args)
    line()
    index = cabinetIndexBuild(root)
    learned = learnedLoad(args.learned)
    rules = rulesLoad(args.config)
    today = dt.date.today()
    for pdf in args.pdfs:
        if not pdf.is_file():
            logger.warning("not a file: %s", pdf)
            continue
        suggestion = suggestionMake(textOfPdf(pdf), pdf.name, index, learned, rules, today)
        print(pdf.name)
        if suggestion is None:
            print("  no suggestion: the folder, type and date dialogs would be shown")
            continue
        print(f"  file as  {suggestion.folder}/{suggestion.fileName() or '(date unknown)'}")
        print(f"  because  {suggestion.reasonText()}")
        for candidate in suggestion.runnerUps:
            print(f"  or       {candidate.folder} ({'; '.join(candidate.reasons)})")
    line()
    logger.done("suggesting")
    return 0


## utilities


def _commonOptions(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.home() / "Documents" / "myCabinets",
        help="cabinets folder (default ~/Documents/myCabinets)",
    )
    parser.add_argument("--config", type=Path, default=configDefaultPath(), help=argparse.SUPPRESS)
    parser.add_argument(
        "--learned", type=Path, default=learnedDefaultPath(), help=argparse.SUPPRESS
    )


def _header(logger, doing: str, root: Path, args: argparse.Namespace) -> None:
    runStart()
    logger.doing(doing)
    logger.value("version", repoVersionRead())
    logger.value("cabinets", root)
    logger.value("rules", args.config)


def _rootValidate(root: Path) -> Path:
    root = root.expanduser()
    if not root.is_dir():
        raise ValueError(f"Cabinets folder not found: {root}")
    return root.resolve()
