#!/usr/bin/env python3
"""
promptFromPhoto.py
Generate structured prompt fragments (pose/location/clothing/etc.) from photos using a vision API.

Design goals:
- works with kohya training root config
- batch process folders recursively
- outputs per-image JSON prompt fragments
- provider-agnostic API (URL + key), JSON contract
- camelCase, log-friendly messages, dry-run support
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

# ============================================================
# logging (prefer organiseMyProjects.logUtils if available)
# ============================================================

def getAppLogger(name: str):
    try:
        # your common package style (as you described)
        from organiseMyProjects.logUtils import getLogger  # type: ignore
        return getLogger(name)
    except Exception:
        import logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)-20s] %(levelname)s %(message)s",
        )
        return logging.getLogger(name)

logger = getAppLogger("promptFromPhoto")


# ============================================================
# config helpers
# ============================================================

DEFAULT_KOHYA_CONFIG_PATH = os.path.expanduser("~/.config/kohya/kohyaConfig.json")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass
class AppConfig:
    apiUrl: str
    apiKey: str
    modelName: str
    kohyaConfigPath: str
    inputPath: Optional[str]
    outputDir: str
    recursive: bool
    dryRun: bool
    maxImages: int
    timeoutSec: int
    retryCount: int
    retryBackoffSec: float


def loadJson(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def pickTrainingRoot(kohyaCfg: Dict[str, Any]) -> Optional[str]:
    """
    Try common key names without assuming exact structure.
    """
    candidates = [
        "trainingRoot",
        "trainRoot",
        "datasetRoot",
        "dataRoot",
        "rootDir",
        "kohyaRoot",
    ]
    for k in candidates:
        v = kohyaCfg.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return None


def listImages(inputDir: Path, recursive: bool) -> List[Path]:
    if not inputDir.exists():
        raise FileNotFoundError(f"input path not found: {inputDir}")
    if inputDir.is_file():
        return [inputDir] if inputDir.suffix.lower() in IMAGE_EXTS else []

    pattern = "**/*" if recursive else "*"
    images: List[Path] = []
    for p in inputDir.glob(pattern):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            images.append(p)
    images.sort()
    return images


# ============================================================
# vision api client (provider-agnostic)
# ============================================================

VISION_SYSTEM_PROMPT = """
You are a prompt-fragment extractor for photorealistic SD1.5 generation.
Given a single photo, return ONLY valid JSON matching this schema:

{
  "posePrompt": "string, short SD-friendly phrase",
  "locationPrompt": "string, short SD-friendly phrase",
  "clothingPrompt": "string, short SD-friendly phrase",
  "lightingPrompt": "string, short SD-friendly phrase",
  "cameraPrompt": "string, short SD-friendly phrase",
  "negativesHint": "string, short semicolon-separated hints, optional but preferred",
  "tags": ["string", ... up to 12],
  "confidence": { "pose": 0-1, "location": 0-1, "clothing": 0-1 }
}

Rules:
- Do NOT identify real people. Do NOT guess names.
- Focus on pose, scene/location, clothing, lighting, and camera/composition.
- Keep each prompt fragment concise, comma-separated clauses are ok.
- Use neutral, safe descriptions. Do NOT include explicit sexual content.
- Prefer terms like: "soft natural daylight", "shallow depth of field", "background bokeh", "portrait framing", "35mm lens look", "85mm lens look".
- If unsure, keep it generic rather than hallucinating.
Return JSON only, no markdown, no extra keys.
""".strip()


def encodeImageBase64(imagePath: Path) -> str:
    data = imagePath.read_bytes()
    return base64.b64encode(data).decode("ascii")


def callVisionApi(
    apiUrl: str,
    apiKey: str,
    modelName: str,
    imagePath: Path,
    timeoutSec: int,
    retryCount: int,
    retryBackoffSec: float,
) -> Dict[str, Any]:
    """
    Provider-agnostic contract:
    POST apiUrl
    Headers:
      Authorization: Bearer <apiKey>
      Content-Type: application/json

    Body:
    {
      "model": "<modelName>",
      "system": "<systemPrompt>",
      "image_base64": "<base64>",
      "response_format": "json"
    }

    Expected response JSON:
    { "content": { ...schema... } }
      OR
    { ...schema... }  (some providers return directly)

    Adjust this adapter to match your chosen provider.
    """
    imageB64 = encodeImageBase64(imagePath)

    payload = {
        "model": modelName,
        "system": VISION_SYSTEM_PROMPT,
        "image_base64": imageB64,
        "response_format": "json",
    }

    headers = {
        "Authorization": f"Bearer {apiKey}",
        "Content-Type": "application/json",
    }

    lastErr: Optional[str] = None
    for attempt in range(0, retryCount + 1):
        try:
            resp = requests.post(apiUrl, headers=headers, json=payload, timeout=timeoutSec)
            if resp.status_code == 429:
                lastErr = "rate limited"
                sleepSec = retryBackoffSec * (2 ** attempt)
                logger.info(f"...rate limited, retrying in {sleepSec:.1f}s")
                time.sleep(sleepSec)
                continue
            resp.raise_for_status()

            data = resp.json()
            if isinstance(data, dict) and "content" in data and isinstance(data["content"], dict):
                return data["content"]
            return data  # assume provider returns schema directly

        except Exception as e:
            lastErr = str(e)
            if attempt < retryCount:
                sleepSec = retryBackoffSec * (2 ** attempt)
                logger.info(f"...api call failed, retrying in {sleepSec:.1f}s: {lastErr}")
                time.sleep(sleepSec)
                continue
            break

    raise RuntimeError(f"api call failed: {lastErr}")


# ============================================================
# validation + output
# ============================================================

REQUIRED_KEYS = ["posePrompt", "locationPrompt", "clothingPrompt", "lightingPrompt", "cameraPrompt", "tags", "confidence"]


def validateResult(result: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(result, dict):
        return False, "result is not a json object"
    for k in REQUIRED_KEYS:
        if k not in result:
            return False, f"missing key: {k}"

    if not isinstance(result.get("tags"), list):
        return False, "tags is not a list"
    conf = result.get("confidence")
    if not isinstance(conf, dict):
        return False, "confidence is not an object"
    for ck in ["pose", "location", "clothing"]:
        if ck not in conf:
            return False, f"confidence missing: {ck}"

    return True, "ok"


def writeJson(path: Path, data: Dict[str, Any], dryRun: bool) -> None:
    if dryRun:
        logger.info(f"...dry run, would write: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


# ============================================================
# main
# ============================================================

def parseArgs() -> AppConfig:
    parser = argparse.ArgumentParser(description="generate pose/location/clothing prompt fragments from photos using a vision api")
    parser.add_argument("--config", default=DEFAULT_KOHYA_CONFIG_PATH, help="path to kohyaConfig.json")
    parser.add_argument("--input", default=None, help="image file or folder (overrides trainingRoot from config)")
    parser.add_argument("--out", default="./promptFragments", help="output folder for per-image .prompts.json")
    parser.add_argument("--no-recursive", action="store_true", help="do not scan subfolders")
    parser.add_argument("--dry-run", action="store_true", help="log actions without writing files")
    parser.add_argument("--max-images", type=int, default=0, help="limit images processed (0 = no limit)")
    parser.add_argument("--timeout", type=int, default=60, help="api timeout seconds")
    parser.add_argument("--retries", type=int, default=3, help="retry count for api errors / rate limits")
    parser.add_argument("--backoff", type=float, default=2.0, help="retry backoff base seconds")

    # provider settings via env, with flags as override
    parser.add_argument("--api-url", default=os.environ.get("PROMPT_API_URL", ""), help="vision api url (or env PROMPT_API_URL)")
    parser.add_argument("--api-key", default=os.environ.get("PROMPT_API_KEY", ""), help="vision api key (or env PROMPT_API_KEY)")
    parser.add_argument("--model", default=os.environ.get("PROMPT_API_MODEL", "vision-model"), help="vision model name (or env PROMPT_API_MODEL)")

    args = parser.parse_args()

    if not args.api_url:
        raise SystemExit("missing --api-url (or PROMPT_API_URL)")
    if not args.api_key:
        raise SystemExit("missing --api-key (or PROMPT_API_KEY)")

    return AppConfig(
        apiUrl=args.api_url,
        apiKey=args.api_key,
        modelName=args.model,
        kohyaConfigPath=args.config,
        inputPath=args.input,
        outputDir=args.out,
        recursive=not args.no_recursive,
        dryRun=args.dry_run,
        maxImages=args.max_images,
        timeoutSec=args.timeout,
        retryCount=args.retries,
        retryBackoffSec=args.backoff,
    )


def main() -> int:
    cfg = parseArgs()

    logger.info("...loading kohya config")
    kohyaCfg = loadJson(cfg.kohyaConfigPath)

    inputPath = cfg.inputPath
    if not inputPath:
        trainingRoot = pickTrainingRoot(kohyaCfg)
        if not trainingRoot:
            logger.error("ERROR Kohya config has no recognizable training root key.")
            return 2
        inputPath = trainingRoot

    inputDir = Path(inputPath)
    outDir = Path(cfg.outputDir)

    logger.info(f"...input path: {inputDir}")
    logger.info(f"...output dir: {outDir}")
    logger.info(f"...recursive: {cfg.recursive}")
    logger.info(f"...dry run: {cfg.dryRun}")

    images = listImages(inputDir, cfg.recursive)
    if cfg.maxImages and cfg.maxImages > 0:
        images = images[: cfg.maxImages]

    logger.info(f"...images found: {len(images)}")
    if not images:
        logger.info("...nothing to do")
        return 0

    for idx, imgPath in enumerate(images, start=1):
        rel = imgPath.relative_to(inputDir) if imgPath.is_relative_to(inputDir) else imgPath.name
        outPath = outDir / str(rel)  # mirror folder structure
        outPath = outPath.with_suffix(outPath.suffix + ".prompts.json")

        logger.info(f"...[{idx}/{len(images)}] processing: {rel}")

        if outPath.exists():
            logger.info("...skip (output exists)")
            continue

        if cfg.dryRun:
            logger.info("...dry run, skip api call")
            continue

        result = callVisionApi(
            apiUrl=cfg.apiUrl,
            apiKey=cfg.apiKey,
            modelName=cfg.modelName,
            imagePath=imgPath,
            timeoutSec=cfg.timeoutSec,
            retryCount=cfg.retryCount,
            retryBackoffSec=cfg.retryBackoffSec,
        )

        ok, msg = validateResult(result)
        if not ok:
            logger.error(f"ERROR Invalid api result for {rel}: {msg}")
            # still write raw for debugging
            rawPath = outPath.with_suffix(outPath.suffix + ".raw.json")
            writeJson(rawPath, {"raw": result, "error": msg}, dryRun=False)
            continue

        writeJson(outPath, result, dryRun=False)
        logger.info("...written")

    logger.info("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
