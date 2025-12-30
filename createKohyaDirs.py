#!/usr/bin/env python3
"""
createKohyaDirs.py

Prepare Kohya training folders using the logical structure:

  baseDataDir/
    styleName/
      train/
      output/
      originals/   (optional)

Actions:
- Move top-level image files from style folder into style/train
- Move matching .txt captions if they exist
- If caption missing, create a default caption

Undo:
- Move files back from style/train into style root (flat)

Examples:
  python createKohyaDirs.py
  python createKohyaDirs.py --style kathy
  python createKohyaDirs.py --dryRun
  python createKohyaDirs.py --undo --style kathy
  python createKohyaDirs.py --baseDataDir /mnt/otherDisk/datasets
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from kohyaUtils import (
    KohyaPaths,
    buildDefaultCaption,
    ensureDirs,
    getCaptionPath,
    isImageFile,
    resolveKohyaPaths,
    writeCaptionIfMissing,
)


defaultBaseDataDir = Path("/mnt/myVideo/Adult/tumblrForMovie")


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or restore Kohya training folder structure (style/train).")

    parser.add_argument(
        "--baseDataDir",
        type=Path,
        default=defaultBaseDataDir,
        help=f"root folder containing style folders (default: {defaultBaseDataDir})",
    )

    parser.add_argument(
        "--style",
        type=str,
        default=None,
        help="process only a specific style folder (e.g., 'kathy'). If omitted, processes all style folders.",
    )

    parser.add_argument(
        "--undo",
        action="store_true",
        help="restore from style/train back to a flat style folder structure",
    )

    parser.add_argument(
        "--dryRun",
        action="store_true",
        help="show what would be done without changing anything",
    )

    parser.add_argument(
        "--captionTemplate",
        type=str,
        default="{token}, photo",
        help="caption template used when creating missing captions (default: '{token}, photo')",
    )

    parser.add_argument(
        "--captionExtension",
        type=str,
        default=".txt",
        help="caption extension (default: .txt)",
    )

    parser.add_argument(
        "--includeOriginalsDir",
        action="store_true",
        help="also create style/originals directory (optional)",
    )

    parser.add_argument(
        "--copy",
        action="store_true",
        help="copy files instead of moving them (default is move)",
    )

    return parser.parse_args()


def getStyleFolders(baseDataDir: Path, styleNameFilter: Optional[str]) -> List[Path]:
    if not baseDataDir.is_dir():
        raise FileNotFoundError(f"baseDataDir does not exist or is not a directory: {baseDataDir}")

    if styleNameFilter:
        styleDir = baseDataDir / styleNameFilter
        if not styleDir.is_dir():
            raise FileNotFoundError(f"style folder not found: {styleDir}")
        return [styleDir]

    # All first-level directories under baseDataDir are treated as style folders
    return sorted([p for p in baseDataDir.iterdir() if p.is_dir()])


def listTopLevelImages(styleDir: Path) -> List[Path]:
    """
    Only images in the style root, not recursive.
    Skips known subfolders and any other directories.
    """
    skipDirs = {"train", "output", "originals"}
    images: List[Path] = []

    for entry in styleDir.iterdir():
        if entry.is_dir():
            # Skip known subfolders (and any other dirs)
            continue

        if isImageFile(entry):
            images.append(entry)

    return sorted(images)


def moveOrCopyFile(srcPath: Path, destPath: Path, copyMode: bool, dryRun: bool) -> None:
    if dryRun:
        action = "copy" if copyMode else "move"
        print(f"  [] would {action}: {srcPath.name} -> {destPath}")
        return

    destPath.parent.mkdir(parents=True, exist_ok=True)

    if copyMode:
        import shutil
        shutil.copy2(srcPath, destPath)
    else:
        srcPath.rename(destPath)


def processStyleFolder(
    styleDir: Path,
    captionTemplate: str,
    captionExtension: str,
    dryRun: bool,
    includeOriginalsDir: bool,
    copyMode: bool,
) -> None:
    styleName = styleDir.name
    paths = resolveKohyaPaths(styleName=styleName, baseDataDir=styleDir.parent)

    print(f"\nProcessing: {styleDir}")
    print(f"  train folder: {paths.trainDir}")
    print(f"  output folder: {paths.outputDir}")
    print(f"  caption template: {captionTemplate}")
    if dryRun:
        print("  [DRY RUN MODE] - no files will be modified")

    ensureDirs(paths, includeOriginals=includeOriginalsDir)

    images = listTopLevelImages(styleDir)
    if not images:
        print("  ...no top-level images found, nothing to do.")
        return

    defaultCaption = buildDefaultCaption(styleName=styleName, template=captionTemplate)

    movedImages = 0
    movedCaptions = 0
    createdCaptions = 0

    for imagePath in images:
        destImagePath = paths.trainDir / imagePath.name

        if destImagePath.exists():
            print(f"  ...image already in train: {imagePath.name}")
        else:
            print(f"  ...{('copying' if copyMode else 'moving')} image: {imagePath.name}")
            moveOrCopyFile(imagePath, destImagePath, copyMode=copyMode, dryRun=dryRun)
            movedImages += 1

        # caption handling
        srcCaptionPath = getCaptionPath(imagePath, captionExtension=captionExtension)
        destCaptionPath = getCaptionPath(destImagePath, captionExtension=captionExtension)

        if destCaptionPath.exists():
            # already good
            continue

        if srcCaptionPath.exists():
            print(f"    ...{('copying' if copyMode else 'moving')} caption: {srcCaptionPath.name}")
            moveOrCopyFile(srcCaptionPath, destCaptionPath, copyMode=copyMode, dryRun=dryRun)
            movedCaptions += 1
        else:
            print(f"    ...creating caption: {destCaptionPath.name}")
            if writeCaptionIfMissing(
                imagePath=destImagePath,
                captionText=defaultCaption,
                captionExtension=captionExtension,
                dryRun=dryRun,
            ):
                createdCaptions += 1

    print()
    print(f"  done. images handled: {len(images)}")
    print(f"  images {('copied' if copyMode else 'moved')}: {movedImages}")
    print(f"  captions {('copied' if copyMode else 'moved')}: {movedCaptions}")
    print(f"  captions created: {createdCaptions}")


def undoStyleFolder(
    styleDir: Path,
    captionExtension: str,
    dryRun: bool,
    copyMode: bool,
) -> None:
    styleName = styleDir.name
    paths = resolveKohyaPaths(styleName=styleName, baseDataDir=styleDir.parent)

    print(f"\nRestoring (undo): {styleDir}")
    print(f"  moving files from: {paths.trainDir}")
    if dryRun:
        print("  [DRY RUN MODE] - no files will be modified")

    if not paths.trainDir.exists():
        print("  ...no train folder found, skipping.")
        return

    moved = 0
    skipped = 0

    for entry in sorted(paths.trainDir.iterdir()):
        if not entry.is_file():
            continue

        destPath = styleDir / entry.name
        if destPath.exists():
            print(f"  ...file already exists in style root, skipping: {entry.name}")
            skipped += 1
            continue

        print(f"  ...{('copying' if copyMode else 'moving')} back: {entry.name}")
        moveOrCopyFile(entry, destPath, copyMode=copyMode, dryRun=dryRun)
        moved += 1

    # attempt to remove empty train folder (only if move mode and not dryRun)
    if not dryRun and not copyMode:
        try:
            if paths.trainDir.exists() and not any(paths.trainDir.iterdir()):
                paths.trainDir.rmdir()
                print("  ...removed empty train folder")
        except Exception as e:
            print(f"  WARNING: could not remove train folder: {e}")

    print()
    print(f"  done. files moved back: {moved}, skipped: {skipped}")


def main() -> None:
    args = parseArgs()

    baseDataDir = args.baseDataDir.expanduser().resolve()

    try:
        styleFolders = getStyleFolders(baseDataDir, args.style)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    if args.undo:
        print(f"Undoing train structure in: {baseDataDir}")
        for styleDir in styleFolders:
            undoStyleFolder(
                styleDir=styleDir,
                captionExtension=args.captionExtension,
                dryRun=args.dryRun,
                copyMode=args.copy,
            )
        print("\nFinished! Your folders have been restored to flat structure (style root).")
        return

    print(f"Scanning: {baseDataDir}")
    for styleDir in styleFolders:
        processStyleFolder(
            styleDir=styleDir,
            captionTemplate=args.captionTemplate,
            captionExtension=args.captionExtension,
            dryRun=args.dryRun,
            includeOriginalsDir=args.includeOriginalsDir,
            copyMode=args.copy,
        )

    print("\nFinished! Your folders are now Kohya-ready (style/train).")


if __name__ == "__main__":
    main()
