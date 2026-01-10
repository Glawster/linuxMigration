#!/usr/bin/env python3
"""
copyToComfui.py

Scan a training directory for images and:
- detect faces
- classify faces into full-body / half-body / portrait
- detect low-resolution images
- copy matches into ComfyUI input subfolders

Config (optional): ~/.config/kohya/kohyaConfig.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple

import cv2


# ============================================================
# logging helpers
# ============================================================

def prefixFor(dryRun: bool) -> str:
    return "...[]" if dryRun else "..."


def logInfo(msg: str) -> None:
    print(msg)


def logError(msg: str) -> None:
    print(f"ERROR: {msg}")


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
# config loader
# ============================================================

def loadKohyaConfig() -> dict:
    configPath = Path.home() / ".config" / "kohya" / "kohyaConfig.json"
    if not configPath.exists():
        return {}

    try:
        with configPath.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except Exception as ex:
        logError(f"Failed to load config: {configPath} ({ex})")
        return {}


def getNestedDictValue(config: dict, keys: Tuple[str, ...]) -> Optional[object]:
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
            if p.suffix.lower() in IMAGE_EXTS:
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


def classifyFraming(largestFace, cfg: FramingConfig) -> str:
    _, _, _, faceH, _, imgH = largestFace
    ratio = faceH / float(imgH)

    if ratio <= cfg.fullBodyMaxFaceRatio:
        return "full_body"
    if ratio <= cfg.halfBodyMaxFaceRatio:
        return "half_body"
    return "portrait"


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


def copyFile(srcPath: Path, destDir: Path, dryRun: bool, tag: str, extra: str = "") -> None:
    prefix = prefixFor(dryRun)
    destPath = uniqueDestPath(destDir, srcPath)
    extraPart = f" {extra}" if extra else ""
    logInfo(f"{prefix} {tag}: {srcPath} -> {destPath}{extraPart}")

    if not dryRun:
        shutil.copy2(srcPath, destPath)


# ============================================================
# main
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Copy training images into ComfyUI buckets.")
    parser.add_argument("--source", help="Training root (overrides config)")
    parser.add_argument("--dest", help="ComfyUI input folder (overrides config)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-dir", action="append", default=[])
    parser.add_argument("--include-portrait", action="store_true")

    args = parser.parse_args()

    config = loadKohyaConfig()

    trainingRoot = config.get("trainingRoot")
    comfyInput = getNestedDictValue(config, ("comfyUI", "inputDir"))
    configSkipDirs = set(config.get("skipDirs", []))

    sourceRoot = Path(args.source or trainingRoot).expanduser().resolve()
    destRoot = Path(args.dest or comfyInput).expanduser().resolve()

    if not sourceRoot.exists():
        logError("Training root does not exist")
        raise SystemExit(2)

    skipDirs = set(DEFAULT_SKIP_DIRS)
    skipDirs.update(configSkipDirs)
    skipDirs.update(args.skip_dir)

    lowResCfg = LowResConfig(
        minShortSide=int(getNestedDictValue(config, ("lowRes", "minShortSide")) or DEFAULT_MIN_SHORT_SIDE),
        minPixels=int(getNestedDictValue(config, ("lowRes", "minPixels")) or DEFAULT_MIN_PIXELS),
    )

    framingCfg = FramingConfig(
        fullBodyMaxFaceRatio=float(getNestedDictValue(config, ("framing", "fullBodyMaxFaceRatio")) or 0.18),
        halfBodyMaxFaceRatio=float(getNestedDictValue(config, ("framing", "halfBodyMaxFaceRatio")) or 0.35),
    )

    faceCfg = FaceDetectConfig()
    detector = loadDetector()

    facesFullDir = destRoot / "faces_full_body"
    facesHalfDir = destRoot / "faces_half_body"
    facesPortraitDir = destRoot / "faces_portrait"
    facesLowResDir = destRoot / "faces_lowres"
    lowResDir = destRoot / "lowres"

    prefix = prefixFor(args.dry_run)
    logInfo(f"{prefix} training root: {sourceRoot}")
    logInfo(f"{prefix} comfyui input: {destRoot}")

    for imagePath in iterImages(sourceRoot, skipDirs):
        largestFace = detectLargestFace(imagePath, detector, faceCfg)
        lowRes, w, h = isLowRes(imagePath, lowResCfg)

        sizeInfo = f"[{w}x{h}]" if (w and h) else ""

        if largestFace:
            framing = classifyFraming(largestFace, framingCfg)
            _, _, _, faceH, _, imgH = largestFace
            ratioInfo = f" faceRatio={faceH/imgH:.3f}"

            if lowRes:
                copyFile(imagePath, facesLowResDir, args.dry_run, "faces_lowres", f"{sizeInfo}{ratioInfo}")
            elif framing == "full_body":
                copyFile(imagePath, facesFullDir, args.dry_run, "face_full_body", f"{sizeInfo}{ratioInfo}")
            elif framing == "half_body":
                copyFile(imagePath, facesHalfDir, args.dry_run, "face_half_body", f"{sizeInfo}{ratioInfo}")
            elif args.include_portrait:
                copyFile(imagePath, facesPortraitDir, args.dry_run, "face_portrait", f"{sizeInfo}{ratioInfo}")

        elif lowRes:
            copyFile(imagePath, lowResDir, args.dry_run, "lowres", sizeInfo)


if __name__ == "__main__":
    main()
