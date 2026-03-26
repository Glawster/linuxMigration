#!/usr/bin/env python3
"""
organiseWastebasket.py

Group wastebasket media files into title/season/episode sub-folders.
Files are matched by S00E00 patterns in the filename.

By default this runs as a dry-run and only shows what would be done.
Pass --confirm to actually move files.

Usage:
    python3 organiseWastebasket.py [--source PATH] [--confirm]

Examples:
    python3 organiseWastebasket.py --source ~/Downloads/.wastebasket
    python3 organiseWastebasket.py --source ~/Downloads/.wastebasket --confirm
"""

import re
import shutil
import argparse
from pathlib import Path
from collections import defaultdict


def sourceDirPath(value: str) -> str:
    """Validate source directory argument and return resolved path string."""
    try:
        sourcePath = Path(value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as error:
        raise argparse.ArgumentTypeError(f"Error resolving path '{value}': {error}")

    if not sourcePath.exists():
        raise argparse.ArgumentTypeError(
            f"Source directory does not exist: {sourcePath}"
        )

    if not sourcePath.is_dir():
        raise argparse.ArgumentTypeError(
            f"Source path is not a directory: {sourcePath}"
        )

    return str(sourcePath)


def parseSeasonEpisode(filename: str):
    """
    Extract title, SddEdd, and name from filename.
    Example: title.S00E07.name0001.avi
    """
    # Main pattern
    pattern = r"^(?P<title>.+?)\.(?P<seasonEpisode>S\d{2}E\d{2})\.(?P<name>.+?)(?:\d+)?\.(?P<ext>[^.]+)$"
    match = re.match(pattern, filename, re.IGNORECASE)

    if match:
        title = match.group("title").strip()
        seasonEpisode = match.group("seasonEpisode").upper()
        name = match.group("name").strip()
        return title, seasonEpisode, name

    # Fallback pattern
    fallbackPattern = r"^(?P<title>.+?)\.(?P<seasonEpisode>S\d{2}E\d{2})"
    match2 = re.search(fallbackPattern, filename, re.IGNORECASE)
    if match2:
        title = match2.group("title").strip()
        seasonEpisode = match2.group("seasonEpisode").upper()

        remaining = filename[match2.end() :].strip(".")
        namePart = (
            re.split(r"\d+\.", remaining)[0]
            if re.search(r"\d", remaining)
            else remaining
        )
        name = re.sub(
            r"\.(mp4|avi|mkv|mov)$", "", namePart, flags=re.IGNORECASE
        ).strip()

        if not name or name.lower() in ["unknown", ""]:
            name = "Unknown"
        return title, seasonEpisode, name

    return None, None, None


def sanitizeFolderName(name: str) -> str:
    """
    Remove or replace characters that are invalid in filenames.
    Also strips trailing dots and spaces which cause issues on many filesystems.
    """
    # Replace invalid characters: < > : " / \ | ? *
    sanitized = re.sub(r'[<>:\"/\\|?*]', "_", name)
    # Remove trailing dots and spaces
    return sanitized.strip().rstrip(".")


def groupFilesByFolder(sourceDir: str, confirm: bool = False):
    """
    Group files into folders like: title.S00E07.name/
    """
    sourcePath = Path(sourceDir)
    if not sourcePath.exists():
        print(f"Error: Directory {sourceDir} does not exist!")
        return

    folderGroups = defaultdict(list)

    print("Scanning files...\n")

    for filePath in sourcePath.rglob("*.*"):
        if filePath.is_file():
            isProxy = filePath.parent.name == "Proxy"
            filename = filePath.name

            title, seasonEpisode, name = parseSeasonEpisode(filename)

            if title and seasonEpisode:
                if name and name.lower() not in ["unknown", ""]:
                    folderName = sanitizeFolderName(f"{title}.{seasonEpisode}.{name}")
                else:
                    folderName = sanitizeFolderName(f"{title}.{seasonEpisode}.Unknown")

                folderGroups[folderName].append((filePath, isProxy))
            else:
                print(f"Could not parse: {filename}")

    if not folderGroups:
        print("No files found to organise.")
        return

    # Show summary
    print(f"Found {len(folderGroups)} groups to create:\n")
    for folderName, files in sorted(folderGroups.items()):
        print(f"  {folderName}  ({len(files)} files)")

    # Ask for confirmation if not using --confirm
    if not confirm:
        print("\n" + "=" * 60)
        print("This is a DRY RUN. No files will be moved.")
        print("To actually move the files, run the script with --confirm flag:")
        print("    python organiseWastebasket.py --confirm --source <path>")
        print("=" * 60)
        return

    # === ACTUAL MOVE (only runs with --confirm) ===
    print("\n" + "=" * 60)
    print("CONFIRMED - Starting to organise files...")
    print("=" * 60)

    for folderName, files in folderGroups.items():
        targetFolder = sourcePath / folderName
        targetFolder.mkdir(exist_ok=True)
        print(f"\nCreated folder: {folderName}")

        proxyDirs = set()
        for filePath, isProxy in files:
            dest = targetFolder / filePath.name
            if dest.exists():
                print(f"  Skipping (already exists): {filePath.name}")
            else:
                try:
                    shutil.move(str(filePath), str(dest))
                    print(f"  Moved: {filePath.name}")
                except Exception as e:
                    print(f"  Error moving {filePath.name}: {e}")
            if isProxy:
                proxyDirs.add(filePath.parent)

        for proxyDir in proxyDirs:
            if proxyDir.exists() and not any(proxyDir.iterdir()):
                try:
                    proxyDir.rmdir()
                    print(f"  Removed empty Proxy folder: {proxyDir}")
                except Exception as e:
                    print(f"  Error removing Proxy folder {proxyDir}: {e}")

    print("\n" + "=" * 60)
    print(f"Organisation completed! {len(folderGroups)} folders created.")
    print("=" * 60)


def parseArgs():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Group wastebasket media files into title/season/episode folders."
    )
    parser.add_argument(
        "--source",
        type=sourceDirPath,
        default=".",
        help="Source directory to scan recursively (default: current directory).",
    )
    parser.add_argument(
        "--confirm",
        "-c",
        "--yes",
        action="store_true",
        help="Actually move files. Without this flag, runs as dry-run.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parseArgs()

    print(".wastebasket File Organiser")
    print("-" * 70)

    groupFilesByFolder(args.source, confirm=args.confirm)
