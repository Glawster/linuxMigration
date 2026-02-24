#!/usr/bin/env python3
"""
cleanNames.py

Remove known torrent/index prefixes from file and directory names, then remove
directories that do not contain any video files in their subtree.

Usage:
    python3 cleanNames.py [--source PATH] [--confirm]

Examples:
    python3 cleanNames.py
    python3 cleanNames.py --source ~/Downloads --confirm
"""

import argparse
import os
import re
import shutil

# List of prefixes to remove (add more patterns here if needed)
prefixPatterns = [
    r"^\s*www\.UIndex\.org\s*-\s*",
    r"^\s*www\.Torrenting\.com\s*-\s*",
]

# Combine all patterns into one OR regex (case insensitive)
combinedPattern = "|".join(prefixPatterns)
regex = re.compile(combinedPattern, re.IGNORECASE)

videoExtensions = {
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".wmv",
    ".flv",
    ".webm",
    ".m4v",
    ".mpeg",
    ".mpg",
}


def directoryContainsVideo(directoryPath: str) -> bool:
    """Return True if the directory tree contains at least one video file."""
    for root, _, files in os.walk(directoryPath):
        for fileName in files:
            _, extension = os.path.splitext(fileName)
            if extension.lower() in videoExtensions:
                return True
    return False


def removeDirectoriesWithoutVideos(rootDirectory: str, dryRun: bool = False) -> None:
    """Remove directories that contain no video files in their subtree."""
    for currentRoot, dirNames, _ in os.walk(rootDirectory, topdown=False):
        for dirName in dirNames:
            directoryPath = os.path.join(currentRoot, dirName)

            if os.path.islink(directoryPath):
                continue

            if directoryContainsVideo(directoryPath):
                continue

            try:
                if dryRun:
                    print(
                        f"[DRY-RUN] Would remove directory (no videos found): {directoryPath}"
                    )
                else:
                    shutil.rmtree(directoryPath)
                    print(f"Removed directory (no videos found): {directoryPath}")
            except PermissionError:
                print(f"Error: Permission denied while removing {directoryPath}")
            except OSError as error:
                print(f"Error removing {directoryPath}: {error}")
            except Exception as e:
                print(f"   Error: {e}\n")


def parseArguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Clean known name prefixes and remove directories that contain no video files."
        )
    )
    parser.add_argument(
        "--source",
        default="/mnt/video2/toFile",
        help="Source directory to process (default: /mnt/video2/toFile)",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Execute changes (default is dry-run mode).",
    )
    return parser.parse_args()


def main() -> None:
    args = parseArguments()
    args.dryRun = not args.confirm
    folder = args.source
    dryRun = args.dryRun

    for oldName in os.listdir(folder):
        match = regex.match(oldName)
        if not match:
            continue

        newName = regex.sub("", oldName, count=1)
        newName = newName.strip()

        if newName and newName != oldName:
            oldPath = os.path.join(folder, oldName)
            newPath = os.path.join(folder, newName)

            print(f"  {oldName}")
            print(f"→ {newName}")

            try:
                if dryRun:
                    print("   [DRY-RUN] Would rename\n")
                else:
                    os.rename(oldPath, newPath)
                    print("   ✓ Renamed successfully\n")
            except FileExistsError:
                print("   Error: Target name already exists!\n")
            except PermissionError:
                print("   Error: Permission denied\n")
            except Exception as e:
                print(f"   Error: {e}\n")
        else:
            print(f"Skipped: {oldName} (no change needed)\n")

    removeDirectoriesWithoutVideos(folder, dryRun=dryRun)

    print("Finished.")


if __name__ == "__main__":
    main()
