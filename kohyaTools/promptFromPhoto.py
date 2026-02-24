#!/usr/bin/env python3
"""
promptFromPhoto.py

Generate prompt sidecar JSON files from reference photos using LLaVA.

- One .prompt.json per image
- Human-editable
- No ComfyUI interaction
- Supports dry-run / print / explain / scorecards / golden fixtures

Assumptions:
- Supports a two-pass strategy (description, then structured field extraction when needed).
- Supports two LLaVA response shapes:
  1) structured JSON keys like posePrompt, clothingPrompt, locationPrompt, lightingPrompt,
     cameraPrompt, negativesHint, styleNegative
  2) simple JSON like {ok: true, result: "...description..."} (the full description is stored as positive.description)
"""

from __future__ import annotations

import argparse
import json
import ast
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import requests

from kohyaConfig import loadConfig, getCfgValue, setLogger  # type: ignore
from organiseMyProjects.logUtils import getLogger  # type: ignore

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

FIELD_QUESTIONS = {
    "posePrompt": (
        "Describe the pose of the main subject."
        "Include posture + any leg/arm position if notable. "
        "Examples: 'sitting on a log', 'standing, one leg raised'."
    ),
    "clothingPrompt": (
        "List what the main subject is wearing. "
        "Include key accessories if visible."
    ),
    "locationPrompt": (
        "Describe the setting/location."
        "Examples: 'kitchen', 'living room', 'beach', 'outdoors by trees'."
    ),
    "lightingPrompt": (
        "Describe the lighting."
        "Examples: 'soft indoor light', 'bright daylight', 'dim room light'."
    ),
    "cameraPrompt": (
        "Describe the camera framing/angle."
        "Examples: 'eye-level', 'close-up', 'full-body', 'high angle'."
    ),
}

def dedupeText(text: str) -> str:
    """
    Remove duplicated items while preserving order.
    Example: "red dress, red dress, blue sky" -> "red dress, blue sky"
    """
    seen = set()
    deduped = []
    for part in text.split(","):
        p = part.strip()
        key = p.lower()
        if p and key not in seen:
            seen.add(key)
            deduped.append(p)
    return ", ".join(deduped)

def squashToPromptFragment(text: str) -> str:
    """
    Convert verbose LLaVA prose into a short, prompt-friendly fragment.
    Also removes duplicated items while preserving order.
    """
    if not text:
        return ""

    t = text.strip()

    # remove common boilerplate
    for prefix in [
        "the image shows",
        "in the image",
        "the woman is",
        "this image shows",
        "the lighting conditions are",
        "the camera angle is",
        "she is wearing",
        "she is dressed in",
    ]:
        if t.lower().startswith(prefix):
            t = t[len(prefix):].strip(" ,.")

    # keep only first sentence
    for sep in [".", ";"]:
        if sep in t:
            t = t.split(sep, 1)[0]

    # split into candidate items
    parts = [p.strip() for p in t.replace(" and ", ", ").split(",")]

    # de-duplicate (case-insensitive, preserve order)
    seen = set()
    deduped = []
    for p in parts:
        key = p.lower()
        if p and key not in seen:
            seen.add(key)
            deduped.append(p.lower())

    return _cleanPiece(", ".join(deduped))

def logFieldLayout(logger, imageName: str, llavaJson: Dict[str, Any]) -> None:
    def g(k: str) -> str:
        v = llavaJson.get(k, "")
        return v if isinstance(v, str) else str(v)

    logger.info("field layout: %s", imageName)
    logger.info("...description   : %s", g("description"))
    logger.info("...posePrompt    : %s", g("posePrompt"))
    logger.info("...clothingPrompt: %s", g("clothingPrompt"))
    logger.info("...locationPrompt: %s", g("locationPrompt"))
    logger.info("...lightingPrompt: %s", g("lightingPrompt"))
    logger.info("...cameraPrompt  : %s", g("cameraPrompt"))

def _nowUtcIso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _cleanPiece(value: str) -> str:
    # Keep this deliberately conservative; we want prompts stable.
    return " ".join(str(value).strip().split())


def _joinPieces(pieces: List[str]) -> str:
    cleaned = [_cleanPiece(p) for p in pieces if _cleanPiece(p)]
    return ", ".join(cleaned)


def detectConflicts(text: str) -> List[str]:
    """
    Lightweight conflict checks. Keep it simple so it stays predictable.
    """
    t = text.lower()
    conflicts: List[str] = []

    # Example conflicts (extend as you learn issues from outputs)
    if "lowres" in t and ("high detail" in t or "highly detailed" in t):
        conflicts.append("lowres vs high detail")
    if "blurry" in t and ("sharp" in t or "sharp focus" in t):
        conflicts.append("blurry vs sharp")
    if "jpeg artifacts" in t and ("clean" in t or "pristine" in t):
        conflicts.append("jpeg artifacts vs clean/pristine")

    return conflicts


def promptMetrics(positive: str, negative: str) -> Dict[str, Any]:
    posPieces = [p.strip() for p in positive.split(",") if p.strip()]
    negPieces = [p.strip() for p in negative.split(",") if p.strip()]
    posUnique = len({p.lower() for p in posPieces})
    negUnique = len({p.lower() for p in negPieces})

    posConflicts = detectConflicts(positive)
    negConflicts = detectConflicts(negative)

    return {
        "positive": {
            "chars": len(positive),
            "pieces": len(posPieces),
            "uniquePieces": posUnique,
            "conflicts": posConflicts,
        },
        "negative": {
            "chars": len(negative),
            "pieces": len(negPieces),
            "uniquePieces": negUnique,
            "conflicts": negConflicts,
        },
    }


def buildSidecar(
    *,
    imageName: str,
    llavaJson: Dict[str, Any],
    basePositive: str,
    baseNegative: str,
    identity: str,
    explain: bool,
) -> Dict[str, Any]:
    """Normalize LLaVA output into a stable sidecar format."""

    # Normalize llava fields defensively
    # - structured mode: posePrompt/clothingPrompt/...
    # - simple mode: {ok: true, result: "free text description"}
    description = (
        _cleanPiece(llavaJson.get("result", ""))
        if isinstance(llavaJson.get("result", ""), str)
        else ""
    )

    pose = _cleanPiece(llavaJson.get("posePrompt", ""))
    clothing = _cleanPiece(llavaJson.get("clothingPrompt", ""))
    location = _cleanPiece(llavaJson.get("locationPrompt", ""))
    lighting = _cleanPiece(llavaJson.get("lightingPrompt", ""))
    camera = _cleanPiece(llavaJson.get("cameraPrompt", ""))

    negativesHint = _cleanPiece(llavaJson.get("negativesHint", ""))
    styleNegative = _cleanPiece(llavaJson.get("styleNegative", ""))

    positive = {
        "identity": identity,
        "description": description,
        "pose": pose,
        "clothing": clothing,
        "location": location,
        "lighting": lighting,
        "camera": camera,
    }

    negative = {
        "general": negativesHint,
        "style": styleNegative,
    }

    assembledPositive = _joinPieces([basePositive, *positive.values()])
    assembledNegative = _joinPieces([baseNegative, *negative.values()])

    sidecar: Dict[str, Any] = {
        "sourceImage": imageName,
        "generator": {
            "tool": "llava",
            "timestamp": _nowUtcIso(),
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
        "metrics": promptMetrics(assembledPositive, assembledNegative),
    }

    if explain:
        why: List[str] = []
        if _cleanPiece(basePositive):
            why.append("added basePositive from config")
        if _cleanPiece(baseNegative):
            why.append("added baseNegative from config")
        if identity:
            why.append("set identity from config/arg")

        for k in ["description", "pose", "clothing", "location", "lighting", "camera"]:
            if positive.get(k):
                why.append(f"added positive.{k} from llava")
        for k in ["general", "style"]:
            if negative.get(k):
                why.append(f"added negative.{k} from llava")

        # If there are conflicts, call them out so you spot prompt issues quickly
        posConf = sidecar["metrics"]["positive"]["conflicts"]
        negConf = sidecar["metrics"]["negative"]["conflicts"]
        if posConf:
            why.append(f"positive conflicts detected: {', '.join(posConf)}")
        if negConf:
            why.append(f"negative conflicts detected: {', '.join(negConf)}")

        sidecar["explain"] = why

    return sidecar


def parseArgs(cfg: Dict[str, Any]) -> argparse.Namespace:
    p = argparse.ArgumentParser("Generate prompt sidecars from photos")
    p.add_argument("--input", type=Path, default=Path(getCfgValue(cfg, "comfyInput")))
    p.add_argument("--remote", required=True, default=getCfgValue(cfg, "llavaUrl"))

    p.add_argument(
        "--question",
        default=str(
            getCfgValue(
                cfg,
                "llavaQuestion",
                "Describe the image in detail. Pay particular attention to pose and clothing.",
            )
        ),
        help="question/instruction sent to llava",
    )

    p.add_argument(
        "--identity", default=str(getCfgValue(cfg, "comfyText2ImgIdentity", "kathy"))
    )

    p.add_argument("--force", action="store_true", help="overwrite existing sidecars")
    p.add_argument(
        "--confirm",
        action="store_true",
        help="execute changes (default is dry-run mode)",
    )
    p.add_argument(
        "--print",
        dest="printPrompts",
        action="store_true",
        help="print assembled prompts to stdout",
    )
    p.add_argument(
        "--explain", action="store_true", help="include explain[] reasons in sidecar"
    )
    p.add_argument(
        "--scorecard", action="store_true", help="log prompt metrics per image"
    )

    p.add_argument(
        "--only",
        type=str,
        default="",
        help="process only files whose name contains this text",
    )
    p.add_argument(
        "--limit", type=int, default=0, help="process at most N images (0 = no limit)"
    )

    p.add_argument(
        "--fixture-out",
        type=Path,
        default=None,
        help="if set, write golden fixture jsons here as <imageName>.expected.prompt.json (never overwrites unless --force)",
    )
    return p.parse_args()


def postToLlava(llavaUrl: str, img: Path, question: str) -> Dict[str, Any]:
    # Note: content-type should match actual file; but most servers are fine with octet-stream.
    # We keep it simple and stable.
    with img.open("rb") as f:
        r = requests.post(
            llavaUrl,
            files={"image": (img.name, f, "application/octet-stream")},
            data={"question": question},
            timeout=300,
        )
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("LLaVA response is not a json object")

    # If server returns {ok: false, ...}, surface it as an error early
    if "ok" in data and not bool(data.get("ok")):
        raise ValueError(f"llava returned ok=false: {str(data)[:500]}")

    return data

def askSingleField(llavaUrl: str, img: Path, question: str) -> str:
    """
    Ask LLaVA a single, focused question (with image) and return result as cleaned text.
    This avoids brittle JSON-only extraction on /analyze endpoints.
    """
    resp = postToLlava(llavaUrl, img, question)
    val = resp.get("result", "")
    return _cleanPiece(val) if isinstance(val, str) else ""

def listImages(inputDir: Path, onlyContains: str) -> List[Path]:
    images = [
        p for p in inputDir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    if onlyContains:
        images = [p for p in images if onlyContains.lower() in p.name.lower()]
    return sorted(images)


def main() -> int:

    cfg = loadConfig()
    args = parseArgs(cfg)
    dryRun = True
    if args.confirm:
        dryRun = False

    llavaUrl = str(args.remote).strip()
    if args.remote:
        # identify if this is a Pod ID or full URL
        if "://" not in str(args.remote):
            podId = str(args.remote).strip()
            port = 9188
            if not podId:
                raise ValueError("invalid ComfyUI Pod ID")
            llavaUrl = f"https://{podId}-{int(port)}.proxy.runpod.net/analyze"

    logger = getLogger("promptFromPhoto", includeConsole=True)
    setLogger(logger)

    inputDir = args.input.expanduser().resolve()
    if not inputDir.exists():
        logger.error("Input dir does not exist: %s", inputDir)
        return 2

    basePositive = str(getCfgValue(cfg, "comfyText2ImgBasePositive", ""))
    baseNegative = str(getCfgValue(cfg, "comfyText2ImgBaseNegative", ""))

    images = listImages(inputDir, args.only)
    if args.limit and args.limit > 0:
        images = images[: args.limit]

    logger.info("found images: %d", len(images))
    logger.info("...input dir: %s", inputDir)
    logger.info("...llava url: %s", llavaUrl)
    logger.info("...question: %s", args.question)
    logger.info("...identity: %s", args.identity)
    logger.info("...dry run: %s", bool(dryRun))

    fixtureOut: Optional[Path] = (
        args.fixture_out.expanduser().resolve() if args.fixture_out else None
    )
    if fixtureOut:
        fixtureOut.mkdir(parents=True, exist_ok=True)
        logger.info("...fixture out: %s", fixtureOut)

    processed = 0

    for img in images:
        sidecarPath = img.with_suffix(".prompt.json")

        if sidecarPath.exists() and not args.force:
            logger.info("skip (sidecar exists): %s", img.name)
            continue

        logger.info("analyzing: %s", img.name)

        try:
            llavaJson = postToLlava(llavaUrl, img, args.question)

            # second-pass extraction (robust): ask focused questions per field (still uses /analyze with image)
            try:
                logger.info("...extracting fields (per-question)")
                for key, q in FIELD_QUESTIONS.items():
                    if not _cleanPiece(llavaJson.get(key, "")):
                        logger.info("...asking llava: %s", key)
                        ans = askSingleField(llavaUrl, img, q)
                        ans = dedupeText(ans)
                        if key == "posePrompt":
                            logger.info("...pose raw resp: %s", ans)
                        #ans = squashToPromptFragment(ans)
                        if ans:
                            llavaJson[key] = ans

                logFieldLayout(logger, img.name, llavaJson)

                logger.info(
                    "...extracted: pose=%s clothing=%s location=%s lighting=%s camera=%s",
                    _cleanPiece(llavaJson.get("posePrompt", "")),
                    _cleanPiece(llavaJson.get("clothingPrompt", "")),
                    _cleanPiece(llavaJson.get("locationPrompt", "")),
                    _cleanPiece(llavaJson.get("lightingPrompt", "")),
                    _cleanPiece(llavaJson.get("cameraPrompt", "")),
                )
            except Exception as e:
                logger.error("Failed to extract fields for %s: %s", img.name, e)

            sidecarData = buildSidecar(
                imageName=img.name,
                llavaJson=llavaJson,
                basePositive=basePositive,
                baseNegative=baseNegative,
                identity=args.identity,
                explain=bool(args.explain),
            )

            if args.scorecard:
                m = sidecarData["metrics"]
                logger.info(
                    "...scorecard: posPieces=%s posUnique=%s posChars=%s posConflicts=%s",
                    m["positive"]["pieces"],
                    m["positive"]["uniquePieces"],
                    m["positive"]["chars"],
                    (
                        ",".join(m["positive"]["conflicts"])
                        if m["positive"]["conflicts"]
                        else "none"
                    ),
                )
                logger.info(
                    "...scorecard: negPieces=%s negUnique=%s negChars=%s negConflicts=%s",
                    m["negative"]["pieces"],
                    m["negative"]["uniquePieces"],
                    m["negative"]["chars"],
                    (
                        ",".join(m["negative"]["conflicts"])
                        if m["negative"]["conflicts"]
                        else "none"
                    ),
                )

            if args.printPrompts:
                print(f"\n== {img.name} ==")
                print("POSITIVE:")
                print(sidecarData["assembled"]["positive"])
                print("\nNEGATIVE:")
                print(sidecarData["assembled"]["negative"])
                print("")

            # fixture output (golden)
            if fixtureOut:
                fixturePath = fixtureOut / f"{img.name}.expected.prompt.json"
                if fixturePath.exists() and not args.force:
                    logger.info("skip (fixture exists): %s", fixturePath.name)
                else:
                    fixturePath.write_text(
                        json.dumps(sidecarData, indent=2), encoding="utf-8"
                    )
                    logger.info("wrote fixture: %s", fixturePath.name)

            if dryRun:
                logger.info("...dry run: not writing sidecar")
            else:
                sidecarPath.write_text(
                    json.dumps(sidecarData, indent=2), encoding="utf-8"
                )
                logger.info("wrote sidecar: %s", sidecarPath.name)

            processed += 1

        except requests.HTTPError as e:
            logger.error("Failed to call llava for %s: %s", img.name, e)
        except Exception as e:
            logger.error("Failed to process %s: %s", img.name, e)

    logger.info("done. processed: %d", processed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
