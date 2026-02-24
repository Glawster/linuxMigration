#!/usr/bin/env python3
"""
copyToComfyUI.py

Forward mode (default):
- scan trainingRoot for images (ignores backup files with .orig., .orig_*, or __orig in filename)
- detect faces
- classify framing into full-body / half-body / portrait (heuristic)
- detect low-resolution images
- bucket rules:
    - if low-res => copy to input/lowres (regardless of face/framing)
    - else if face => copy to input/faces_full_body or faces_half_body or faces_portrait
- log what happened (no CSV report)

Reverse mode (--reverse):
- scan ComfyUI inputDir for subdirectories whose name starts with "fixed"
- scan ComfyUI outputDir (if provided) for files whose name starts with "fixed_" (flat folder)
- for each image found, infer kohya style from filename and copy back to:
    trainingRoot/<style>/10_<style>/<filename>
- BEFORE overwrite, backup existing original by renaming it with suffix "__orig"
- overwrite mode is always on; --dry-run shows operations without executing

Config (optional): ~/.config/kohya/kohyaConfig.json
Expected keys (examples):
{
  "trainingRoot": "/mnt/backup",
  "comfyInput": "/home/andy/Source/ComfyUI/input",
  "comfyOutput": "/home/andy/Source/ComfyUI/output",
  "skipDirs": [".wastebasket", ".Trash", "@eaDir"],
  "lowRes": { "minShortSide": 768, "minPixels": 589824 },
  "framing": { "fullBodyMaxFaceRatio": 0.18, "halfBodyMaxFaceRatio": 0.35 }
}
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple

import cv2

from kohyaConfig import loadConfig, saveConfig, updateConfigFromArgs, DEFAULT_CONFIG_PATH  # type: ignore
from organiseMyProjects.logUtils import getLogger  # type: ignore


# ============================================================
# constants
# ============================================================

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

DEFAULT_SKIP_DIRS = {
    ".wastebasket",
    ".trash",
    ".Trash",
    ".Trash-1000",
    ".Trashes",
    "@eaDir",
    ".AppleDouble",
    ".DS_Store",
}

DEFAULT_MIN_SHORT_SIDE = 768
DEFAULT_MIN_PIXELS = 768 * 768

# filename pattern: 20221217-pretty-01.png  OR  2022-12-17-pretty-01.png  OR  ...-01a.png
# Also supports ComfyUI fixed_ prefix: fixed_20221217-pretty-01_00001_.png
STYLE_FROM_FILENAME_RE = re.compile(
    r"^(?:fixed_)?(?:\d{8}|\d{4}-\d{2}-\d{2})-(?P<style>.+?)-\d+(?:[a-z])?(?:_\d+_)?\.[^.]+$",
    re.IGNORECASE,
)


# ============================================================
# dataclasses
# ============================================================

@dataclass(frozen=True)
class FaceDetectConfig:
    scaleFactor: float = 1.1
    minNeighbors: int = 5
    minSize: int = 40


@dataclass(frozen=True)
class LowResConfig:
    minShortSide: int
    minPixels: int


@dataclass(frozen=True)
class FramingConfig:
    fullBodyMaxFaceRatio: float = 0.18
    halfBodyMaxFaceRatio: float = 0.35


# ============================================================
# config helpers
# ============================================================

def getNestedDictValue(config: dict, keys: Tuple[str, ...]) -> Optional[object]:
    """Get a nested dictionary value using a tuple of keys."""
    node: object = config
    for k in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(k)
    return node


# ============================================================
# scanning helpers
# ============================================================

def iterImages(root: Path, skipDirs: set[str]) -> Iterable[Path]:
    for dirPath, dirNames, fileNames in os.walk(root):
        dirNames[:] = [d for d in dirNames if d not in skipDirs]
        for name in fileNames:
            p = Path(dirPath) / name
            # Skip files with .orig. or .orig_* or __orig in the filename
            # These are backup/processed files that should not be re-copied
            # Examples: file.orig.jpg, file.orig_01.png, file.orig_backup.png, file__orig.jpg
            # Does NOT filter: file.original.jpg, myOriginal.jpg
            name_lower = name.lower()
            if ".orig." in name_lower or ".orig_" in name_lower or "__orig" in name_lower:
                continue
            if p.suffix.lower() in IMAGE_EXTS:
                yield p


def iterImagesAny(root: Path) -> Iterable[Path]:
    """Recursive image iterator without skip-dirs (used for fixed folders)."""
    for dirPath, _, fileNames in os.walk(root):
        for name in fileNames:
            p = Path(dirPath) / name
            if p.suffix.lower() in IMAGE_EXTS:
                yield p


def isFixedFolder(path: Path) -> bool:
    return path.is_dir() and path.name.lower().startswith("fixed")


def iterFixedFolders(root: Path) -> Iterable[Path]:
    """Yield all directories named fixed* under root (recursive)."""
    for dirPath, dirNames, _ in os.walk(root):
        for d in dirNames:
            p = Path(dirPath) / d
            if isFixedFolder(p):
                yield p


# ============================================================
# face detection + framing
# ============================================================

def loadDetector() -> cv2.CascadeClassifier:
    cascadePath = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(str(cascadePath))
    if detector.empty():
        raise RuntimeError(f"could not load haar cascade: {cascadePath}")
    return detector

def loadPeopleDetector() -> cv2.HOGDescriptor:
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
    return hog

def detectLargestFace(
    imagePath: Path,
    detector: cv2.CascadeClassifier,
    cfg: FaceDetectConfig,
):
    img = cv2.imread(str(imagePath))
    if img is None:
        return None

    imgH, imgW = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    faces = detector.detectMultiScale(
        gray,
        scaleFactor=cfg.scaleFactor,
        minNeighbors=cfg.minNeighbors,
        minSize=(cfg.minSize, cfg.minSize),
    )

    if len(faces) == 0:
        return None

    x, y, w, h = max(faces, key=lambda r: int(r[2]) * int(r[3]))
    return (int(x), int(y), int(w), int(h), int(imgW), int(imgH))

def detectLargestPerson(
    imagePath: Path,
    hog: cv2.HOGDescriptor,
) -> Optional[Tuple[int, int, int, int, int, int]]:
    """
    Returns (x, y, w, h, imgW, imgH) for the largest detected person bbox.
    Uses OpenCV HOG people detector (fast, no external weights).
    """
    img = cv2.imread(str(imagePath))
    if img is None:
        return None

    imgH, imgW = img.shape[:2]

    # HOG works better with some reasonable size; don’t overthink it.
    # (We are only using this to confirm "feet likely in frame".)
    rects, _ = hog.detectMultiScale(img, winStride=(8, 8), padding=(8, 8), scale=1.05)

    if rects is None or len(rects) == 0:
        return None

    x, y, w, h = max(rects, key=lambda r: int(r[2]) * int(r[3]))
    return (int(x), int(y), int(w), int(h), int(imgW), int(imgH))


def hasFeetInFrame(
    personBBox: Tuple[int, int, int, int, int, int],
    feetBottomThreshold: float = 0.95,
) -> bool:
    """
    True if the bottom of the person bbox is close to the image bottom.
    """
    x, y, w, h, imgW, imgH = personBBox
    bottom = y + h
    return bottom >= int(imgH * feetBottomThreshold)

def classifyFraming(
    largestFace,
    framingCfg: FramingConfig,
    personBBox: Optional[Tuple[int, int, int, int, int, int]],
) -> Tuple[str, float]:
    """
    Returns (framing, faceRatio)

    Rules:
      - full_body: face present AND feet visible
      - half_body: face present AND feet NOT visible
      - portrait: face dominates frame
    """
    _, _, _, faceH, _, imgH = largestFace
    ratio = faceH / float(imgH)

    # portrait: face is large
    if ratio > framingCfg.halfBodyMaxFaceRatio:
        return ("portrait", ratio)

    # candidate for full body by face size
    if ratio <= framingCfg.fullBodyMaxFaceRatio:
        if personBBox is not None and hasFeetInFrame(personBBox, feetBottomThreshold=0.95):
            return ("full_body", ratio)
        # face but no feet → half body
        return ("half_body", ratio)

    # remaining face-containing images
    return ("half_body", ratio)


# ============================================================
# low-res detection
# ============================================================

def getImageSize(imagePath: Path) -> Optional[Tuple[int, int]]:
    img = cv2.imread(str(imagePath))
    if img is None:
        return None
    h, w = img.shape[:2]
    return (w, h)


def isLowRes(imagePath: Path, cfg: LowResConfig) -> Tuple[bool, Optional[int], Optional[int]]:
    size = getImageSize(imagePath)
    if size is None:
        return (False, None, None)

    w, h = size
    shortSide = min(w, h)
    pixels = w * h

    low = (shortSide < cfg.minShortSide) or (pixels < cfg.minPixels)
    return (low, w, h)


# ============================================================
# copy helpers
# ============================================================

def uniqueDestPath(destDir: Path, srcPath: Path) -> Path:
    destDir.mkdir(parents=True, exist_ok=True)

    base = srcPath.stem
    ext = srcPath.suffix.lower()

    candidate = destDir / f"{base}{ext}"
    if not candidate.exists():
        return candidate

    i = 1
    while True:
        candidate = destDir / f"{base}_{i:03d}{ext}"
        if not candidate.exists():
            return candidate
        i += 1


def copyFile(srcPath: Path, destDir: Path, dryRun: bool, tag: str, extra: str = "") -> Path:
    destPath = uniqueDestPath(destDir, srcPath)
    extraPart = f" {extra}" if extra else ""
    logger.info(f"{prefix} {tag}: {srcPath} -> {destPath}{extraPart}")

    if not dryRun:
        shutil.copy2(srcPath, destPath)

    return destPath


# ============================================================
# reverse helpers (fixed -> trainingRoot)
# ============================================================

def styleFromFilename(filePath: Path) -> Optional[str]:
    m = STYLE_FROM_FILENAME_RE.match(filePath.name)
    if not m:
        return None
    style = m.group("style").strip()
    return style or None


def uniqueBackupPath(originalPath: Path, suffix: str = "__orig") -> Path:
    """
    If /path/file.png exists, produce:
      /path/file__orig.png
    If that exists:
      /path/file__orig_001.png
    etc.
    """
    base = originalPath.stem
    ext = originalPath.suffix
    candidate = originalPath.with_name(f"{base}{suffix}{ext}")
    if not candidate.exists():
        return candidate

    i = 1
    while True:
        candidate = originalPath.with_name(f"{base}{suffix}_{i:03d}{ext}")
        if not candidate.exists():
            return candidate
        i += 1


def backupThenCopyReplace(srcFixed: Path, destOriginal: Path, dryRun: bool) -> None:
    """
    Always overwrite, but first backup any existing destOriginal by renaming it.
    Then copy srcFixed to destOriginal.
    """

    destOriginal.parent.mkdir(parents=True, exist_ok=True)

    if destOriginal.exists():
        backupPath = uniqueBackupPath(destOriginal, suffix="__orig")
        logger.info(f"{prefix} backup: {destOriginal} -> {backupPath}")
        if not dryRun:
            destOriginal.rename(backupPath)

    logger.info(f"{prefix} replace: {srcFixed} -> {destOriginal}")
    if not dryRun:
        shutil.copy2(srcFixed, destOriginal)


def reverseFromFixedFolders(
    trainingRoot: Path,
    comfyIn: Path,
    comfyOut: Optional[Path],
    dryRun: bool,
) -> None:

    scanned = 0
    replaced = 0
    errors = 0

    # Process input folder: look for fixed_* subdirectories
    if comfyIn.exists():
        fixedFolders = list(iterFixedFolders(comfyIn))
        if fixedFolders:
            logger.info(f"{prefix} found {len(fixedFolders)} fixed folder(s) under input")
            for fixedFolder in fixedFolders:
                logger.info(f"{prefix} fixed folder (input): {fixedFolder}")

                for fixedImg in iterImagesAny(fixedFolder):
                    scanned += 1

                    style = styleFromFilename(fixedImg)
                    if not style:
                        errors += 1
                        logger.error(f"Cannot determine style from filename: {fixedImg.name}")
                        continue

                    destDir = trainingRoot / style / f"10_{style}"
                    destOriginal = destDir / fixedImg.name

                    try:
                        backupThenCopyReplace(fixedImg, destOriginal, dryRun)
                        replaced += 1
                    except Exception as ex:
                        errors += 1
                        logger.error(f"Failed to replace {destOriginal.name}: {ex}")

    # Process output folder: treat as flat folder, look for fixed_* files directly
    if comfyOut is not None and comfyOut.exists():
        fixedFiles = [p for p in comfyOut.iterdir() if p.is_file() and p.name.lower().startswith("fixed_") and p.suffix.lower() in IMAGE_EXTS]
        
        if fixedFiles:
            logger.info(f"{prefix} found {len(fixedFiles)} fixed file(s) in output folder")
            
            for fixedImg in fixedFiles:
                scanned += 1

                style = styleFromFilename(fixedImg)
                if not style:
                    errors += 1
                    logger.error(f"Cannot determine style from filename: {fixedImg.name}")
                    continue

                destDir = trainingRoot / style / f"10_{style}"
                destOriginal = destDir / fixedImg.name

                try:
                    backupThenCopyReplace(fixedImg, destOriginal, dryRun)
                    replaced += 1
                except Exception as ex:
                    errors += 1
                    logger.error(f"Failed to replace {destOriginal.name}: {ex}")

    if scanned == 0:
        logger.info(f"{prefix} no fixed folders or files found under input/output")

    logger.info(f"{prefix} reversing scanned: {scanned}")
    logger.info(f"{prefix} reversing replaced: {replaced}")
    logger.info(f"{prefix} reversing errors: {errors}")


# ============================================================
# main
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser(description="Copy training images into ComfyUI buckets (logging only, no CSV report).")
    parser.add_argument("--training", help="Training root (overrides config)")
    parser.add_argument("--comfyin", help="ComfyUI input folder (overrides config)")
    parser.add_argument("--comfyout", help="ComfyUI output folder (overrides config)")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="execute changes (default is dry-run mode)",
    )
    parser.add_argument("--skip-dir", action="append", default=[])
    parser.add_argument("--include-portrait", action="store_true")
    parser.add_argument("--reverse", action="store_true",
                        help="Reverse mode: scan fixed* folders under ComfyUI input/output and replace originals in trainingRoot (with backup).")

    args = parser.parse_args()
    dryRun = True
    if args.confirm:
        dryRun = False

    global logger
    logger = getLogger("copyToComfyUI", includeConsole=True)

    global prefix
    prefix = "...[]" if dryRun else "..."

    logger.info(f"{prefix} dry run enabled")

    config = loadConfig()

    # resolve config values
    trainingRootCfg = config.get("trainingRoot")
    comfyInputCfg = config.get("comfyInput")
    comfyOutputCfg = config.get("comfyOutput")
    configSkipDirs = set(config.get("skipDirs", [])) if isinstance(config.get("skipDirs", []), list) else set()

    # track config changes for auto-save
    configUpdates: dict = {}

    if args.training:
        configUpdates["trainingRoot"] = args.training

    if args.comfyin:
        configUpdates["comfyInput"] = args.comfyin

    if args.comfyout:
        configUpdates["comfyOutput"] = args.comfyout

    # validate required paths
    trainingRootVal = args.training or trainingRootCfg
    comfyInVal = args.comfyin or comfyInputCfg
    comfyOutVal = args.comfyout or comfyOutputCfg

    if not trainingRootVal:
        logger.error("Training root not provided (use --training or set trainingRoot in config)")
        raise SystemExit(2)
    if not comfyInVal:
        logger.error("ComfyUI input folder not provided (use --comfyin or set comfyInput in config)")
        raise SystemExit(2)

    trainingRoot = Path(str(trainingRootVal)).expanduser().resolve()
    comfyInput = Path(str(comfyInVal)).expanduser().resolve()
    comfyOutput = Path(str(comfyOutVal)).expanduser().resolve() if comfyOutVal else None

    if not trainingRoot.exists():
        logger.error("Training root does not exist")
        raise SystemExit(2)

    # update config if CLI args provided new values
    configChanged = updateConfigFromArgs(config, configUpdates)
    if configChanged and not dryRun:
        saveConfig(config)
    if configChanged:
        logger.info(f"{prefix} updated config: {DEFAULT_CONFIG_PATH}")

    logger.info(f"{prefix} training root: {trainingRoot}")
    logger.info(f"{prefix} comfyui input: {comfyInput}")
    if comfyOutput is not None:
        logger.info(f"{prefix} comfyui output: {comfyOutput}")

    # reverse mode: fixed -> trainingRoot (with backup)
    if args.reverse:
        reverseFromFixedFolders(
            trainingRoot=trainingRoot,
            comfyIn=comfyInput,
            comfyOut=comfyOutput,
            dryRun=dryRun,
        )
        return

    # forward mode: trainingRoot -> comfyui input buckets
    skipDirs = set(DEFAULT_SKIP_DIRS)
    skipDirs.update(configSkipDirs)
    skipDirs.update(args.skip_dir)

    lowResMinShort = int(getNestedDictValue(config, ("lowRes", "minShortSide")) or DEFAULT_MIN_SHORT_SIDE)
    lowResMinPixels = int(getNestedDictValue(config, ("lowRes", "minPixels")) or DEFAULT_MIN_PIXELS)

    lowResCfg = LowResConfig(
        minShortSide=lowResMinShort,
        minPixels=lowResMinPixels,
    )

    framingCfg = FramingConfig(
        fullBodyMaxFaceRatio=float(getNestedDictValue(config, ("framing", "fullBodyMaxFaceRatio")) or 0.18),
        halfBodyMaxFaceRatio=float(getNestedDictValue(config, ("framing", "halfBodyMaxFaceRatio")) or 0.35),
    )

    faceCfg = FaceDetectConfig()
    detector = loadDetector()
    peopleDetector = loadPeopleDetector()

    # buckets (under ComfyUI input)
    fullBodyDir = comfyInput / "fullbody"
    halfBodyDir = comfyInput / "halfbody"
    portraitDir = comfyInput / "portrait"
    lowResDir = comfyInput / "lowres"

    logger.info(f"{prefix} lowres thresholds: minShortSide={lowResCfg.minShortSide}, minPixels={lowResCfg.minPixels}")
    logger.info(
        f"{prefix} framing thresholds: fullBodyMaxFaceRatio={framingCfg.fullBodyMaxFaceRatio}, "
        f"halfBodyMaxFaceRatio={framingCfg.halfBodyMaxFaceRatio}"
    )

    scanned = 0
    matched = 0
    copied = 0
    errors = 0

    for imagePath in iterImages(trainingRoot, skipDirs):
        scanned += 1

        try:
            lowRes, w, h = isLowRes(imagePath, lowResCfg)

            largestFace = detectLargestFace(imagePath, detector, faceCfg)
            hasFace = largestFace is not None

            destDir: Optional[Path] = None
            tag = ""
            extra = ""

            # low-res overrides any face/framing buckets
            if lowRes:
                destDir = lowResDir
                tag = "lowres"
                extra = f"[{w}x{h}]" if (w and h) else ""

            # not low-res: if face then classify framing
            elif hasFace:
                personBBox = detectLargestPerson(imagePath, peopleDetector)
                framing, faceRatio = classifyFraming(largestFace, framingCfg, personBBox)

                extra = f"[{w}x{h}] framing={framing} faceRatio={faceRatio:.3f}" if (w and h) else f"framing={framing} faceRatio={faceRatio:.3f}"

                if framing == "full_body":
                    destDir = fullBodyDir
                    tag = "full_body"
                elif framing == "half_body":
                    destDir = halfBodyDir
                    tag = "half_body"
                else:
                    if args.include_portrait:
                        destDir = portraitDir
                        tag = "portrait"
                    else:
                        # portrait detected but not requested
                        destDir = None
                logger.info(
                    f"...framing decision: {imagePath.name} "
                    f"faceRatio={faceRatio:.3f} feet={'yes' if personBBox and hasFeetInFrame(personBBox) else 'no'} "
                    f"-> {framing}"
                )

            if destDir is None:
                continue

            matched += 1

            _ = copyFile(imagePath, destDir, dryRun, tag, extra)
            copied += 1

        except Exception as ex:
            errors += 1
            logger.error(f"Failed to process {imagePath}: {ex}")

    logger.info(f"{prefix} scanned: {scanned}")
    logger.info(f"{prefix} matched: {matched}")
    logger.info(f"{prefix} copied: {copied}")
    logger.info(f"{prefix} errors: {errors}")


if __name__ == "__main__":
    main()
