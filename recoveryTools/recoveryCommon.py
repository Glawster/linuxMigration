#!/usr/bin/env python3
"""
recoveryCommon.py

Shared constants and helpers for PhotoRec recovery pipeline.
"""

import time
from pathlib import Path
from typing import Iterable

# ----------------------------------------------------------------------
# File type definitions
# ----------------------------------------------------------------------

IMAGE_EXTS = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp",
    ".heic", ".cr2", ".nef",
}

VIDEO_EXTS = {
    ".mp4", ".mov", ".avi", ".mkv", ".mpg", ".mpeg",
    ".mts", ".m2ts", ".wmv", ".3gp",
}


def isImage(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def isVideo(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


def isRelativeTo(path: Path, parent: Path) -> bool:
    """
    Check if path is relative to parent directory.
    Compatible with Python 3.8+ (is_relative_to was added in 3.9).
    """
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


# ----------------------------------------------------------------------
# Progress bar helpers
# ----------------------------------------------------------------------

def formatEta(seconds: float) -> str:
    if seconds <= 0 or seconds != seconds:
        return "--:--:--"
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 99:
        return "99:59:59"
    return f"{h:02d}:{m:02d}:{s:02d}"


def printProgress(
    done: int,
    total: int,
    startTime: float,
    *,
    width: int = 40,
    label: str = "Scanning",
):
    if total <= 0:
        return

    ratio = min(done / total, 1.0)
    filled = int(width * ratio)
    bar = "#" * filled + "-" * (width - filled)
    pct = int(ratio * 100)

    elapsed = time.time() - startTime
    remaining = ((total - done) * elapsed / done) if done > 0 else 0
    etaStr = formatEta(remaining)

    print(
        f"\r{label}: [{bar}] {pct:3d}% ({done}/{total}) ETA {etaStr}",
        end="",
        flush=True,
    )


# ----------------------------------------------------------------------
# File counting / walking helpers
# ----------------------------------------------------------------------

def countFiles(paths: Iterable[Path]) -> int:
    total = 0
    for p in paths:
        if p.is_dir():
            for f in p.rglob("*"):
                if f.is_file():
                    total += 1
        elif p.is_file():
            total += 1
    return total


def iterFiles(paths: Iterable[Path]):
    for p in paths:
        if p.is_dir():
            yield from (f for f in p.rglob("*") if f.is_file())
        elif p.is_file():
            yield p


# ----------------------------------------------------------------------
# Logging helper
# ----------------------------------------------------------------------

def openStepLog(root: Path, name: str):
    """
    Open a line-buffered log file for a pipeline step.
    """
    logPath = root / f"{name}.log"
    log = logPath.open("a", encoding="utf-8", buffering=1)
    print(f"writing log to {logPath}")
    return log
