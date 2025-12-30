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
- Move/copy top-level image files from style folder into style/train
- Rename files as they are moved into train: "{style} #nn.ext"
- Move/copy matching .txt captions if they exist (renamed to match)
- If caption missing, create a default caption

Undo:
- Move/copy files back from style/train into style root (flat)
- Do NOT rename back (keeps "{style} #nn.ext")

Examples:
  python createKohyaDirs.py
  python createKohyaDirs.py --style kathy
  python createKohyaDirs.py --dry-run
  python createKohyaDirs.py --undo --style kathy
  python createKohyaDirs.py --baseDataDir /mnt/otherDisk/datasets
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple

from kohyaTools.kohyaUtils import (
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
        help="restore from style/train back to a flat style folder structure (keeps renamed filenames).",
    )

    parser.add_argument(
        "--dry-run",
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

    return sorted([p for p in baseDataDir.iterdir() if p.is_dir()])


def listTopLevelImages(styleDir: Path) -> List[Path]:
    """
    Only images in the style root, not recursive.
    """
    images: List[Path] = []
    for entry in styleDir.iterdir():
        if entry.is_dir():
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


def formatIndex(index: int) -> str:
    # matches "{style} #nn" with at least two digits (keeps growing if >99)
    if index < 100:
        return f"{index:02d}"
    if index < 1000:
        return f"{index:03d}"
    return str(index)


def buildTargetStem(styleName: str, index: int) -> str:
    return f"{styleName} #{formatIndex(index)}"


def findUsedIndices(trainDir: Path, styleName: str) -> Set[int]:
    """
    Detect existing files in trainDir that already follow "{style} #nn.ext"
    so we can continue numbering without collisions.
    """
    used: Set[int] = set()
    if not trainDir.exists():
        return used

    # accept 2+ digits: "kathy #01", "kathy #001", etc.
    pattern = re.compile(rf"^{re.escape(styleName)}\s+#(\d+)$", re.IGNORECASE)

    for entry in trainDir.iterdir():
        if not entry.is_file():
            continue
        stem = entry.stem
        match = pattern.match(stem)
        if match:
            try:
                used.add(int(match.group(1)))
            except ValueError:
                pass

    return used


def nextAvailableIndex(usedIndices: Set[int], startAt: int = 1) -> int:
    index = startAt
    while index in usedIndices:
        index += 1
    usedIndices.add(index)
    return index


def processStyleFolder(
    styleDir: Path,
    captionTemplate: str,
    captionExtension: str,
    dryRun: bool,
    includeOriginalsDir: bool,
    copyMode: bool,
) -> None:
    prefix = "[] " if dryRun else ""

    styleName = styleDir.name
    paths = resolveKohyaPaths(styleName=styleName, baseDataDir=styleDir.parent)

    print(f"\n...{prefix} processing: {styleDir}")
    print(f"...{prefix} train folder: {paths.trainDir}")
    print(f"...{prefix} output folder: {paths.outputDir}")
    print(f"...{prefix} caption template: {captionTemplate}")

    ensureDirs(paths, includeOriginals=includeOriginalsDir)

    images = listTopLevelImages(styleDir)
    if not images:
        print(f"...{prefix} no top-level images found, nothing to do.")
        return

    defaultCaption = buildDefaultCaption(styleName=styleName, template=captionTemplate)

    usedIndices = findUsedIndices(paths.trainDir, styleName=styleName)

    movedImages = 0
    movedCaptions = 0
    createdCaptions = 0
    skipped = 0

    for imagePath in images:
        # pick next {style} #nn.ext name in train
        index = nextAvailableIndex(usedIndices)
        targetStem = buildTargetStem(styleName, index)
        destImagePath = (paths.trainDir / targetStem).with_suffix(imagePath.suffix.lower())

        # avoid accidental collisions (e.g. different case extensions)
        if destImagePath.exists():
            print(f"{prefix} skipping (already exists): {destImagePath.name}")
            skipped += 1
            continue

        print(f"{prefix} {('copying' if copyMode else 'moving')} image: {imagePath.name} -> {destImagePath.name}")
        moveOrCopyFile(imagePath, destImagePath, copyMode=copyMode, dryRun=dryRun)
        movedImages += 1

        # caption handling:
        # - if src caption exists beside original, move/copy it to match new filename
        # - else create new caption beside dest image
        srcCaptionPath = getCaptionPath(imagePath, captionExtension=captionExtension)
        destCaptionPath = getCaptionPath(destImagePath, captionExtension=captionExtension)

        if destCaptionPath.exists():
            continue

        if srcCaptionPath.exists():
            print(f"{prefix} {('copying' if copyMode else 'moving')} caption: {srcCaptionPath.name} -> {destCaptionPath.name}")
            moveOrCopyFile(srcCaptionPath, destCaptionPath, copyMode=copyMode, dryRun=dryRun)
            movedCaptions += 1
        else:
            print(f"{prefix} creating caption: {destCaptionPath.name}")
            if writeCaptionIfMissing(
                imagePath=destImagePath,
                captionText=defaultCaption,
                captionExtension=captionExtension,
                dryRun=dryRun,
            ):
                createdCaptions += 1

    print(f"{prefix} done. images handled: {len(images)}")
    print(f"{prefix} images {('copied' if copyMode else 'moved')}: {movedImages}")
    print(f"{prefix} captions {('copied' if copyMode else 'moved')}: {movedCaptions}")
    print(f"{prefix} captions created: {createdCaptions}")
    if skipped:
        print(f"{prefix} skipped: {skipped}")


def undoStyleFolder(
    styleDir: Path,
    captionExtension: str,
    dryRun: bool,
    copyMode: bool,
) -> None:
    prefix = "...[]" if dryRun else "..."

    styleName = styleDir.name
    paths = resolveKohyaPaths(styleName=styleName, baseDataDir=styleDir.parent)

    print(f"\n{prefix} restoring (undo): {styleDir}")
    print(f"{prefix} {('copying' if copyMode else 'moving')} files from: {paths.trainDir}")

    if not paths.trainDir.exists():
        print(f"{prefix}no train folder found, skipping.")
        return

    moved = 0
    skipped = 0

    for entry in sorted(paths.trainDir.iterdir()):
        if not entry.is_file():
            continue

        # keep the renamed filename as-is
        destPath = styleDir / entry.name
        if destPath.exists():
            print(f"{prefix} skipping (already exists in style root): {entry.name}")
            skipped += 1
            continue

        print(f"{prefix} {('copying' if copyMode else 'moving')} back: {entry.name}")
        moveOrCopyFile(entry, destPath, copyMode=copyMode, dryRun=dryRun)
        moved += 1

    # attempt to remove empty train folder (only if move mode and not dryRun)
    if not dryRun and not copyMode:
        try:
            if paths.trainDir.exists() and not any(paths.trainDir.iterdir()):
                paths.trainDir.rmdir()
                print(f"{prefix} removed empty train folder")
        except Exception as e:
            print(f"WARNING: could not remove train folder: {e}")

    print(f"{prefix} done. files moved back: {moved}, skipped: {skipped}")


def main() -> None:
    args = parseArgs()

    baseDataDir = args.baseDataDir.expanduser().resolve()

    try:
        styleFolders = getStyleFolders(baseDataDir, args.style)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    if args.undo:
        prefix = "...[]" if args.dry_run else "..."
        print(f"{prefix} undoing train structure in: {baseDataDir}")

        for styleDir in styleFolders:
            undoStyleFolder(
                styleDir=styleDir,
                captionExtension=args.captionExtension,
                dryRun=args.dry_run,
                copyMode=args.copy,
            )
        print(f"{prefix} finished")
        return

    prefix = "...[]" if args.dry_run else "..."
    print(f"{prefix} scanning: {baseDataDir}")
    for styleDir in styleFolders:
        processStyleFolder(
            styleDir=styleDir,
            captionTemplate=args.captionTemplate,
            captionExtension=args.captionExtension,
            dryRun=args.dry_run,
            includeOriginalsDir=args.includeOriginalsDir,
            copyMode=args.copy,
        )

    print(f"{prefix} finished")


if __name__ == "__main__":
    main()
