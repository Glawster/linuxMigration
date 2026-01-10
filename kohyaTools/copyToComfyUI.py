#!/usr/bin/env python3
"""
copyToComfui.py

Scan a training directory for images and:
- detect faces
- classify faces into full-body / half-body / portrait (heuristic)
- detect low-resolution images
- copy matches into ComfyUI input subfolders
- write a CSV report

Config (optional): ~/.config/kohya/kohyaConfig.json

Example config additions:
{
  "trainingRoot": "/mnt/backup",
  "comfyUI": { "inputDir": "/home/andy/Source/ComfyUI/input" },
  "skipDirs": [".wastebasket", ".Trash", "@eaDir"],
  "lowRes": { "minShortSide": 768, "minPixels": 589824 },
  "framing": { "fullBodyMaxFaceRatio": 0.18, "halfBodyMaxFaceRatio": 0.35 }
}
"""

from __future__ import annotations

import argparse
import csv
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


def classifyFraming(largestFace, cfg: FramingConfig) -> Tuple[str, float]:
    """
    Returns (framing, faceRatio) where faceRatio = faceHeight / imageHeight
    """
    _, _, _, faceH, _, imgH = largestFace
    ratio = faceH / float(imgH)

    if ratio <= cfg.fullBodyMaxFaceRatio:
        return ("full_body", ratio)
    if ratio <= cfg.halfBodyMaxFaceRatio:
        return ("half_body", ratio)
    return ("portrait", ratio)


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
    prefix = prefixFor(dryRun)
    destPath = uniqueDestPath(destDir, srcPath)
    extraPart = f" {extra}" if extra else ""
    logInfo(f"{prefix} {tag}: {srcPath} -> {destPath}{extraPart}")

    if not dryRun:
        shutil.copy2(srcPath, destPath)

    return destPath


# ============================================================
# report helpers
# ============================================================

REPORT_FIELDS = [
    "srcPath",
    "destPath",
    "bucket",
    "copied",
    "hasFace",
    "framing",
    "faceRatio",
    "isLowRes",
    "width",
    "height",
    "shortSide",
    "pixels",
    "lowResMinShortSide",
    "lowResMinPixels",
    "error",
]


def defaultReportPath(sourceRoot: Path) -> Path:
    return sourceRoot / "copyToComfui_report.csv"


def writeCsvReport(reportPath: Path, rows: list[dict], dryRun: bool, append: bool) -> None:
    prefix = prefixFor(dryRun)
    reportPath.parent.mkdir(parents=True, exist_ok=True)

    mode = "a" if append and reportPath.exists() else "w"
    writeHeader = (mode == "w")

    with reportPath.open(mode, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=REPORT_FIELDS, extrasaction="ignore")
        if writeHeader:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)

    logInfo(f"{prefix} report: {reportPath}")


# ============================================================
# main
# ============================================================

def main() -> None:
    parser = argparse.ArgumentParser(description="Copy training images into ComfyUI buckets and write a CSV report.")
    parser.add_argument("--source", help="Training root (overrides config)")
    parser.add_argument("--dest", help="ComfyUI input folder (overrides config)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-dir", action="append", default=[])
    parser.add_argument("--include-portrait", action="store_true")

    parser.add_argument("--report", default="",
                        help="CSV report path. Default: <trainingRoot>/copyToComfui_report.csv")
    parser.add_argument("--append-report", action="store_true",
                        help="Append to report if it already exists.")

    args = parser.parse_args()

    config = loadKohyaConfig()

    trainingRoot = config.get("trainingRoot")
    comfyInput = getNestedDictValue(config, ("comfyUI", "inputDir"))
    configSkipDirs = set(config.get("skipDirs", [])) if isinstance(config.get("skipDirs", []), list) else set()

    if not (args.source or trainingRoot):
        logError("Training root not provided (use --source or set trainingRoot in config)")
        raise SystemExit(2)
    if not (args.dest or comfyInput):
        logError("ComfyUI input folder not provided (use --dest or set comfyUI.inputDir in config)")
        raise SystemExit(2)

    sourceRoot = Path(args.source or trainingRoot).expanduser().resolve()
    destRoot = Path(args.dest or comfyInput).expanduser().resolve()

    if not sourceRoot.exists():
        logError("Training root does not exist")
        raise SystemExit(2)

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

    # output buckets
    facesFullDir = destRoot / "faces_full_body"
    facesHalfDir = destRoot / "faces_half_body"
    facesPortraitDir = destRoot / "faces_portrait"
    facesLowResDir = destRoot / "faces_lowres"
    lowResDir = destRoot / "lowres"

    # report target
    reportPath = Path(args.report).expanduser().resolve() if args.report else defaultReportPath(sourceRoot)

    prefix = prefixFor(args.dry_run)
    logInfo(f"{prefix} training root: {sourceRoot}")
    logInfo(f"{prefix} comfyui input: {destRoot}")
    logInfo(f"{prefix} report path: {reportPath}")
    logInfo(f"{prefix} lowres thresholds: minShortSide={lowResCfg.minShortSide}, minPixels={lowResCfg.minPixels}")
    logInfo(f"{prefix} framing thresholds: fullBodyMaxFaceRatio={framingCfg.fullBodyMaxFaceRatio}, "
            f"halfBodyMaxFaceRatio={framingCfg.halfBodyMaxFaceRatio}")

    rows: list[dict] = []

    scanned = 0
    matched = 0
    copied = 0
    errors = 0

    for imagePath in iterImages(sourceRoot, skipDirs):
        scanned += 1

        row = {
            "srcPath": str(imagePath),
            "destPath": "",
            "bucket": "",
            "copied": False,
            "hasFace": False,
            "framing": "",
            "faceRatio": "",
            "isLowRes": False,
            "width": "",
            "height": "",
            "shortSide": "",
            "pixels": "",
            "lowResMinShortSide": lowResCfg.minShortSide,
            "lowResMinPixels": lowResCfg.minPixels,
            "error": "",
        }

        try:
            lowRes, w, h = isLowRes(imagePath, lowResCfg)
            row["isLowRes"] = bool(lowRes)

            if w is not None and h is not None:
                row["width"] = w
                row["height"] = h
                row["shortSide"] = min(w, h)
                row["pixels"] = int(w) * int(h)

            largestFace = detectLargestFace(imagePath, detector, faceCfg)
            hasFace = largestFace is not None
            row["hasFace"] = bool(hasFace)

            destDir: Optional[Path] = None
            bucket = ""
            tag = ""
            extra = ""

            if hasFace:
                framing, faceRatio = classifyFraming(largestFace, framingCfg)
                row["framing"] = framing
                row["faceRatio"] = f"{faceRatio:.4f}"

                extra = f"[{w}x{h}] faceRatio={faceRatio:.3f}" if (w and h) else f"faceRatio={faceRatio:.3f}"

                if lowRes:
                    bucket = "faces_lowres"
                    tag = "faces_lowres"
                    destDir = facesLowResDir
                else:
                    if framing == "full_body":
                        bucket = "faces_full_body"
                        tag = "face_full_body"
                        destDir = facesFullDir
                    elif framing == "half_body":
                        bucket = "faces_half_body"
                        tag = "face_half_body"
                        destDir = facesHalfDir
                    else:
                        if args.include_portrait:
                            bucket = "faces_portrait"
                            tag = "face_portrait"
                            destDir = facesPortraitDir
                        else:
                            # Not copied, but still reportable
                            bucket = "portrait_skipped"
                            destDir = None

            elif lowRes:
                bucket = "lowres"
                tag = "lowres"
                destDir = lowResDir
                extra = f"[{w}x{h}]" if (w and h) else ""

            # no match -> skip report row unless you want full inventory
            if not hasFace and not lowRes:
                continue

            matched += 1
            row["bucket"] = bucket

            if destDir is not None:
                destPath = copyFile(imagePath, destDir, args.dry_run, tag, extra)
                row["destPath"] = str(destPath)
                row["copied"] = True
                copied += 1
            else:
                row["destPath"] = ""
                row["copied"] = False

            rows.append(row)

        except Exception as ex:
            errors += 1
            row["error"] = str(ex)
            rows.append(row)
            logError(f"Failed to process {imagePath}: {ex}")

    writeCsvReport(reportPath, rows, args.dry_run, append=args.append_report)

    logInfo(f"{prefix} scanned: {scanned}")
    logInfo(f"{prefix} matched: {matched}")
    logInfo(f"{prefix} copied: {copied}")
    logInfo(f"{prefix} errors: {errors}")


if __name__ == "__main__":
    main()
