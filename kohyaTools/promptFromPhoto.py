#!/usr/bin/env python3
"""
promptFromPhoto.py

Generate prompt sidecar JSON files from reference photos using LLaVA.

- One .prompt.json per image
- Human-editable
- No ComfyUI interaction
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Dict, Any

import requests

from kohyaConfig import loadConfig, getCfgValue, setLogger  # type: ignore
from organiseMyProjects.logUtils import getLogger  # type: ignore

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def buildSidecar(
    *,
    imageName: str,
    llavaJson: Dict[str, Any],
    basePositive: str,
    baseNegative: str,
) -> Dict[str, Any]:
    """Normalize LLaVA output into a stable sidecar format."""

    positive = {
        "identity": "kathy",
        "pose": llavaJson.get("posePrompt", ""),
        "clothing": llavaJson.get("clothingPrompt", ""),
        "location": llavaJson.get("locationPrompt", ""),
        "lighting": llavaJson.get("lightingPrompt", ""),
        "camera": llavaJson.get("cameraPrompt", ""),
    }

    negative = {
        "general": llavaJson.get("negativesHint", ""),
        "style": llavaJson.get("styleNegative", ""),
    }

    assembledPositive = ", ".join(
        p for p in [basePositive, *positive.values()] if p
    )
    assembledNegative = ", ".join(
        p for p in [baseNegative, *negative.values()] if p
    )

    return {
        "sourceImage": imageName,
        "generator": {
            "tool": "llava",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "positive": positive,
        "negative": negative,
        "assembled": {
            "positive": assembledPositive,
            "negative": assembledNegative,
        },
        "status": {
            "locked": False,
            "notes": "",
        },
    }


def parseArgs(cfg: Dict[str, Any]) -> argparse.Namespace:
    p = argparse.ArgumentParser("Generate prompt sidecars from photos")
    p.add_argument("--input", type=Path, default=Path(getCfgValue(cfg, "comfyInput")))
    p.add_argument("--llavaurl", default=getCfgValue(cfg, "llavaUrl"))
    p.add_argument("--force", action="store_true", help="overwrite existing sidecars")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> int:
    cfg = loadConfig()
    args = parseArgs(cfg)

    logger = getLogger("promptFromPhoto", includeConsole=True)
    setLogger(logger)

    inputDir = args.input.expanduser().resolve()
    if not inputDir.exists():
        logger.error("input dir does not exist: %s", inputDir)
        return 2

    basePositive = str(getCfgValue(cfg, "comfyText2ImgBasePositive", "kathy"))
    baseNegative = str(getCfgValue(cfg, "comfyText2ImgBaseNegative", ""))

    images = [
        p for p in inputDir.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]

    logger.info("found images: %d", len(images))

    for img in images:
        sidecar = img.with_suffix(".prompt.json")

        if sidecar.exists() and not args.force:
            logger.info("skip (sidecar exists): %s", img.name)
            continue

        logger.info("analyzing: %s", img.name)

        if args.dry_run:
            continue

        with img.open("rb") as f:
            r = requests.post(
                args.llavaurl,
                files={"file": (img.name, f, "image/png")},
                timeout=300,
            )
        r.raise_for_status()
        llavaJson = r.json()

        sidecarData = buildSidecar(
            imageName=img.name,
            llavaJson=llavaJson,
            basePositive=basePositive,
            baseNegative=baseNegative,
        )

        sidecar.write_text(json.dumps(sidecarData, indent=2), encoding="utf-8")
        logger.info("wrote sidecar: %s", sidecar.name)

    logger.info("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
