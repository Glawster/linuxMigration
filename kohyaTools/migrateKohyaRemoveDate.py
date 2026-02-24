#!/usr/bin/env python3
"""
migrateKohyaRemoveDate.py

One-off migration:
Rename existing "yyyymmdd-style-nn.ext" or "yyyy-mm-dd-style-nn.ext" files in
trainingRoot/style/10_style to "style-nn.ext".

Collision handling:
- If "style-nn.ext" already exists, allocate the next available index (style-mm.ext).
- The caption file (e.g. .txt) is renamed to match the final chosen image name.

Config:
- reads/writes ~/.config/kohya/kohyaConfig.json (no --configPath)

Logging:
- prefix "...[]" for --dry-run, "..." otherwise
- no "would ..." wording
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple

from organiseMyProjects.logUtils import getLogger  # type: ignore
from kohyaConfig import loadConfig, saveConfig, getCfgValue, updateConfigFromArgs

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

DATE_PREFIX_RE = re.compile(
    r"^(?:\d{8}|\d{4}-\d{2}-\d{2})-(?P<rest>.+)$",
    re.IGNORECASE,
)

# rest must match "style-nn" (style can contain dashes)
REST_STYLE_INDEX_RE = re.compile(r"^(?P<style>.+)-(?P<idx>\d+)$", re.IGNORECASE)


def parseArgs() -> argparse.Namespace:
    cfg = loadConfig()
    defaultTrainingRoot = Path(getCfgValue(cfg, "trainingRoot", str(Path.home())))
    defaultCaptionExtension = str(getCfgValue(cfg, "captionExtension", ".txt"))

    parser = argparse.ArgumentParser(
        description="one-off migration: remove date prefix from kohya 10_style filenames"
    )
    parser.add_argument("--training", type=Path, default=defaultTrainingRoot)
    parser.add_argument("--style", type=str, default=None)
    parser.add_argument("--captionExtension", type=str, default=defaultCaptionExtension)
    parser.add_argument("--confirm", action="store_true")
    return parser.parse_args()


def iterStyleDirs(trainingRoot: Path, styleFilter: Optional[str]) -> Iterable[Path]:
    if not trainingRoot.exists() or not trainingRoot.is_dir():
        raise FileNotFoundError(f"trainingRoot does not exist or is not a directory: {trainingRoot}")

    if styleFilter:
        d = trainingRoot / styleFilter
        if not d.is_dir():
            raise FileNotFoundError(f"style folder not found: {d}")
        yield d
        return

    for d in sorted(trainingRoot.iterdir()):
        if d.is_dir():
            yield d


def trainDirForStyle(styleDir: Path) -> Path:
    style = styleDir.name
    return styleDir / f"10_{style}"


def isImageFile(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS


def parseTargetRest(filename: str) -> Optional[str]:
    """
    If filename matches date-prefix pattern, return the rest (without date-),
    e.g. '20251226-kathy-078.png' -> 'kathy-078.png'
         '2025-12-26-kathy-078.png' -> 'kathy-078.png'
    """
    m = DATE_PREFIX_RE.match(filename)
    if not m:
        return None
    return m.group("rest")


def parseStyleAndIndex(stem: str) -> Optional[Tuple[str, int]]:
    m = REST_STYLE_INDEX_RE.match(stem)
    if not m:
        return None
    style = m.group("style")
    try:
        idx = int(m.group("idx"))
    except ValueError:
        return None
    return style, idx


def formatIndex(idx: int, width: int = 2) -> str:
    return f"{idx:0{width}d}"


def existingIndices(trainDir: Path, styleName: str) -> Set[int]:
    """
    Find indices already present as style-nn.* in this trainDir
    (plus tolerate old date forms just to avoid collisions during migration).
    """
    used: Set[int] = set()

    new_pat = re.compile(rf"^{re.escape(styleName)}-(\d+)$", re.IGNORECASE)
    old_yyyymmdd = re.compile(rf"^\d{{8}}-{re.escape(styleName)}-(\d+)$", re.IGNORECASE)
    old_yyyy_mm_dd = re.compile(rf"^\d{{4}}-\d{{2}}-\d{{2}}-{re.escape(styleName)}-(\d+)$", re.IGNORECASE)

    for p in trainDir.iterdir():
        if not p.is_file():
            continue
        m = new_pat.match(p.stem) or old_yyyymmdd.match(p.stem) or old_yyyy_mm_dd.match(p.stem)
        if not m:
            continue
        try:
            used.add(int(m.group(1)))
        except ValueError:
            pass

    return used


def nextFreeIndex(preferred: int, used: Set[int]) -> int:
    """
    Use preferred if available, otherwise walk upward until free.
    Mutates used set (reserves chosen index).
    """
    idx = preferred
    while idx in used:
        idx += 1
    used.add(idx)
    return idx


def renameSafe(src: Path, dst: Path, dryRun: bool, prefix: str, logger) -> None:
    if src == dst:
        return
    logger.info("%s rename: %s -> %s", prefix, src.name, dst.name)
    if dryRun:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)


def main() -> None:
    args = parseArgs()
    dryRun = True
    if args.confirm:
        dryRun = False
    prefix = "...[]" if dryRun else "..."
    logger = getLogger("migrateKohyaRemoveDate", includeConsole=True)

    trainingRoot = args.training.expanduser().resolve()

    # Persist config (optional, consistent with your tools)
    cfg = loadConfig()
    updates = {"trainingRoot": str(args.training), "captionExtension": str(args.captionExtension)}
    configChanged = updateConfigFromArgs(cfg, updates=updates)
    if configChanged and not dryRun:
        saveConfig(cfg)
    if configChanged:
        logger.info("%s updated config: %s", prefix, Path.home() / ".config/kohya/kohyaConfig.json")

    logger.info("%s scanning: %s", prefix, trainingRoot)

    totalImages = 0
    totalCaptions = 0
    totalSkipped = 0

    for styleDir in iterStyleDirs(trainingRoot, args.style):
        styleName = styleDir.name
        trainDir = trainDirForStyle(styleDir)
        if not trainDir.exists():
            logger.info("%s skip: missing train dir: %s", prefix, trainDir)
            continue

        logger.info("%s style: %s", prefix, styleName)
        used = existingIndices(trainDir, styleName)

        # Process in stable order
        images = [p for p in sorted(trainDir.iterdir()) if isImageFile(p)]
        for img in images:
            restName = parseTargetRest(img.name)
            if not restName:
                continue

            restPath = Path(restName)
            parsed = parseStyleAndIndex(restPath.stem)
            if not parsed:
                logger.info("%s skip: not style-nn after strip: %s", prefix, img.name)
                totalSkipped += 1
                continue

            parsedStyle, preferredIdx = parsed
            if parsedStyle.lower() != styleName.lower():
                logger.info("%s skip: style mismatch (%s != %s): %s", prefix, parsedStyle, styleName, img.name)
                totalSkipped += 1
                continue

            chosenIdx = nextFreeIndex(preferredIdx, used)
            # Keep index width stable with the preferred token width (01 vs 001 etc.)
            # Use same digit count as the original token, minimum 2.
            orig_idx_token = str(preferredIdx)
            width = max(2, len(orig_idx_token))
            newStem = f"{styleName}-{formatIndex(chosenIdx, width=width)}"

            newImg = (trainDir / newStem).with_suffix(img.suffix.lower())

            # caption paths (use original filename base, not stem parsing)
            srcCap = img.with_suffix(args.captionExtension)
            dstCap = newImg.with_suffix(args.captionExtension)

            # If target is same name, this is effectively just stripping date with no collision
            # If collision occurred, chosenIdx will differ and name will change.
            renameSafe(img, newImg, dryRun, prefix, logger)
            totalImages += 1

            if srcCap.exists():
                # If dstCap exists, pick the next free index again? safest is to align with image.
                # If dstCap exists, log error and skip caption rename (don’t overwrite).
                if dstCap.exists() and srcCap != dstCap:
                    logger.error("Destination exists, cannot rename: %s -> %s", srcCap.name, dstCap.name)
                else:
                    renameSafe(srcCap, dstCap, dryRun, prefix, logger)
                    totalCaptions += 1

    logger.info(
        "%s migration summary: images renamed: %d, captions renamed: %d, skipped: %d",
        prefix,
        totalImages,
        totalCaptions,
        totalSkipped,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("ERROR: Interrupted.")
        sys.exit(1)
