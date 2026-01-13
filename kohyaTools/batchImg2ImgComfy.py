#!/usr/bin/env python3
"""
batchImg2ImgComfy.py

Batch-run ComfyUI img2img workflows for images found under ComfyUI input.

Input Precedence Rules:
- For each unique image stem, prefer processed (fixed_*) versions over originals
- If fixed_photo-01_00001_.png exists, use it instead of photo-01.png
- This allows iterative processing without re-processing from scratch

Conventions:
- uses ~/.config/kohya/kohyaConfig.json via kohyaConfig.py (no --configPath)
- logging via organiseMyProjects.logUtils.getLogger
- --dry-run: no side effects (no network calls, no file writes), but logs the same messages
- prefix:
    prefix = "...[]" if args.dryRun else "..."
"""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from kohyaConfig import loadConfig, saveConfig, getCfgValue, updateConfigFromArgs, DEFAULT_CONFIG_PATH  # type: ignore
from organiseMyProjects.logUtils import getLogger  # type: ignore


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class BucketRules:
    name: str
    folderNames: Tuple[str, ...]
    filenameRegexes: Tuple[str, ...]


def safeStem(stem: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", stem).strip("_") or "image"


def classifyImage(path: Path, rules: List[BucketRules]) -> Optional[str]:
    lowerParts = [p.lower() for p in path.parts]
    fileLower = path.name.lower()

    for rule in rules:
        if any(folder.lower() in lowerParts for folder in rule.folderNames):
            return rule.name
        for rx in rule.filenameRegexes:
            if re.search(rx, fileLower):
                return rule.name
    return None


def extractBaseStem(filename: str) -> str:
    """
    Extract the base stem from a filename, removing fixed_ prefix and ComfyUI numbering.
    
    Examples:
        fixed_photo-01_00001_.png -> photo-01
        photo-01.png -> photo-01
        fixed_style-name-01_00002_.png -> style-name-01
    """
    stem = Path(filename).stem
    # Remove fixed_ prefix if present
    if stem.lower().startswith("fixed_"):
        stem = stem[6:]
    # Remove ComfyUI numbering pattern (_00001_)
    stem = re.sub(r"_\d+_$", "", stem)
    return stem


def applyPrecedenceRules(allImages: List[Path]) -> Dict[str, Path]:
    """
    Apply precedence rules: prefer fixed_* versions over originals.
    
    Returns a dict mapping base stem to the image path to use.
    For each unique stem:
    - If a fixed_* version exists, use it (most recent if multiple)
    - Otherwise, use the original
    """
    stemToImages: Dict[str, List[Path]] = {}
    
    for img in allImages:
        baseStem = extractBaseStem(img.name)
        if baseStem not in stemToImages:
            stemToImages[baseStem] = []
        stemToImages[baseStem].append(img)
    
    result: Dict[str, Path] = {}
    for baseStem, images in stemToImages.items():
        # Separate fixed versions from originals
        fixedVersions = [img for img in images if img.name.lower().startswith("fixed_")]
        originals = [img for img in images if not img.name.lower().startswith("fixed_")]
        
        # Prefer fixed version (take the most recent if multiple)
        if fixedVersions:
            # Sort by path (later modifications will have higher numbers)
            result[baseStem] = sorted(fixedVersions)[-1]
        elif originals:
            # Use the original
            result[baseStem] = originals[0]
    
    return result


class ComfyClient:
    def __init__(self, baseUrl: str, timeoutSeconds: int):
        self.baseUrl = baseUrl.rstrip("/")
        self.timeoutSeconds = timeoutSeconds
        self.session = requests.Session()

    def submitPrompt(self, prompt: Dict[str, Any]) -> str:
        url = f"{self.baseUrl}/prompt"
        resp = self.session.post(url, json={"prompt": prompt}, timeout=self.timeoutSeconds)
        resp.raise_for_status()
        data = resp.json()
        promptId = data.get("prompt_id")
        if not promptId:
            raise RuntimeError(f"no prompt_id returned: {data}")
        return promptId

    def getHistory(self, promptId: str) -> Dict[str, Any]:
        url = f"{self.baseUrl}/history/{promptId}"
        resp = self.session.get(url, timeout=self.timeoutSeconds)
        resp.raise_for_status()
        return resp.json()

    def downloadView(self, filename: str, subfolder: str, fileType: str) -> bytes:
        url = f"{self.baseUrl}/view"
        resp = self.session.get(
            url,
            params={"filename": filename, "subfolder": subfolder, "type": fileType},
            timeout=self.timeoutSeconds,
        )
        resp.raise_for_status()
        return resp.content

    def waitForOutputs(self, promptId: str, pollSeconds: float, maxWaitSeconds: int) -> Dict[str, Any]:
        start = time.time()
        while True:
            hist = self.getHistory(promptId)
            if promptId in hist:
                entry = hist[promptId]
                if isinstance(entry, dict) and entry.get("outputs"):
                    return entry
            if time.time() - start > maxWaitSeconds:
                raise TimeoutError(f"timed out waiting for prompt {promptId}")
            time.sleep(pollSeconds)

def hasExistingOutput(outputDir: Path, fixedPrefix: str, stem: str) -> bool:
    """Return True if ComfyUI output already contains fixedPrefix+stem.* (any suffix/counter)."""
    if not outputDir.exists() or not outputDir.is_dir():
        return False

    prefix = f"{fixedPrefix}{stem}"
    # ComfyUI typically writes directly into outputDir, but allow subfolders as well.
    for p in outputDir.rglob("*"):
        if p.is_file() and p.name.startswith(prefix):
            return True
    return False



def loadApiPromptJson(path: Path) -> Dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "prompt" in data and isinstance(data["prompt"], dict):
        return data["prompt"]
    if not isinstance(data, dict):
        raise ValueError("workflow json must be an object/dict")
    return data


def setLoadImageInput(prompt: Dict[str, Any], imageFilename: str) -> int:
    found = 0
    for _, node in prompt.items():
        if isinstance(node, dict) and node.get("class_type") == "LoadImage":
            node.setdefault("inputs", {})["image"] = imageFilename
            found += 1
    return found


def setSaveImagePrefix(prompt: Dict[str, Any], prefixValue: str) -> int:
    found = 0
    for _, node in prompt.items():
        if isinstance(node, dict) and node.get("class_type") == "SaveImage":
            node.setdefault("inputs", {})["filename_prefix"] = prefixValue
            found += 1
    return found


def extractOutputImages(historyEntry: Dict[str, Any]) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    outputs = historyEntry.get("outputs", {})
    if not isinstance(outputs, dict):
        return results

    for _, nodeOut in outputs.items():
        if not isinstance(nodeOut, dict):
            continue
        images = nodeOut.get("images")
        if not isinstance(images, list):
            continue
        for img in images:
            if not isinstance(img, dict):
                continue
            filename = img.get("filename")
            if filename:
                results.append(
                    {
                        "filename": filename,
                        "subfolder": img.get("subfolder", ""),
                        "type": img.get("type", "output"),
                    }
                )
    return results


def renderTemplate(template: str, **kwargs: str) -> str:
    return template.format(**kwargs)


def parseArgs(cfg: Dict[str, Any]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch-run ComfyUI img2img workflows (kohyaConfig.json).")


    parser.add_argument(
        "--dry-run",
        dest="dryRun",
        action="store_true",
        help="show what would be done without changing anything",
    )

    parser.add_argument("--limit", type=int, default=0, help="process at most N images (0 = no limit)")

    parser.add_argument("--comfyurl", default=getCfgValue(cfg, "comfyUrl", "http://127.0.0.1:8188"))
    parser.add_argument("--comfyin", type=Path, default=Path(getCfgValue(cfg, "comfyInput", "./input")))
    parser.add_argument("--comfyout", type=Path, default=Path(getCfgValue(cfg, "comfyOutput", "./output")))
    parser.add_argument("--workflows", type=Path, default=Path(getCfgValue(cfg, "comfyWorkflowsDir", "./workflows")))
    parser.add_argument("--runsdir", type=Path, default=Path(getCfgValue(cfg, "comfyRunsDir", "./runs")))

    parser.add_argument("--timeoutseconds", type=int, default=int(getCfgValue(cfg, "comfyTimeoutSeconds", 60)))
    parser.add_argument("--pollseconds", type=float, default=float(getCfgValue(cfg, "comfyPollSeconds", 1.0)))
    parser.add_argument("--maxwaitseconds", type=int, default=int(getCfgValue(cfg, "comfyMaxWaitSeconds", 1800)))

    parser.add_argument("--loglevel", default=str(getCfgValue(cfg, "comfyLogLevel", "INFO")))
    parser.add_argument("--logconsole", action="store_true", default=bool(getCfgValue(cfg, "comfyLogConsole", True)))

    return parser.parse_args()


def main() -> int:
    cfg = loadConfig()
    args = parseArgs(cfg)

    prefix = "...[]" if args.dryRun else "..."

    logger = getLogger("batchImg2ImgComfy", includeConsole=bool(args.logconsole))

    runStamp = time.strftime("%Y%m%d_%H%M%S")
    runDir = Path(args.runsdir).expanduser().resolve() / f"run_{runStamp}"

    updates = {
        "comfyUrl": str(args.comfyurl),
        "comfyInput": str(Path(args.comfyin).expanduser()),
        "comfyOutput": str(Path(args.comfyout).expanduser()),
        "comfyWorkflowsDir": str(Path(args.workflows).expanduser()),
        "comfyRunsDir": str(Path(args.runsdir).expanduser()),
        "comfyTimeoutSeconds": int(args.timeoutseconds),
        "comfyPollSeconds": float(args.pollseconds),
        "comfyMaxWaitSeconds": int(args.maxwaitseconds),
        "comfyLogLevel": str(args.loglevel).upper(),
        "comfyLogConsole": bool(args.logconsole),
    }

    configChanged = updateConfigFromArgs(cfg, updates)
    if configChanged and not args.dryRun:
        saveConfig(cfg)
    if configChanged:
        logger.info("%s updated config: %s", prefix, DEFAULT_CONFIG_PATH)

    fullWf = Path(args.workflows) / getCfgValue(cfg, "comfyFullbodyWorkflow", "fullbody_api.json")
    halfWf = Path(args.workflows) / getCfgValue(cfg, "comfyHalfbodyWorkflow", "halfbody_api.json")
    portWf = Path(args.workflows) / getCfgValue(cfg, "comfyPortraitWorkflow", "portrait_api.json")

    workflowPaths = {
        "fullbody": fullWf.resolve(),
        "halfbody": halfWf.resolve(),
        "portrait": portWf.resolve(),
    }

    for name, p in workflowPaths.items():
        if not p.exists():
            logger.error("Missing workflow file for %s: %s", name, p)
            return 2

    inputDir = Path(args.comfyin).expanduser().resolve()
    if not inputDir.exists():
        logger.error("Input dir does not exist: %s", inputDir)
        return 2

    # Output folder used to decide whether an image has already been processed.
    # If output already contains "fixed_<stem>*", we skip re-processing; delete the output to regenerate.
    outputDir = Path(args.outputDir) if str(args.outputDir) not in ("", ".") else Path(getCfgValue(cfg, "comfyOutputDir", ""))
    if str(outputDir) in ("", "."):
        outputDir = inputDir.parent / "output"
    outputDir = outputDir.expanduser().resolve()

    fixedPrefix = str(getCfgValue(cfg, "comfyFixedOutputPrefix", "fixed_"))

    rules = [
        BucketRules(
            "fullbody",
            tuple(getCfgValue(cfg, "comfyFullbodyFolders", ["fullbody", "full-body", "full_body", "full"])),
            tuple(getCfgValue(cfg, "comfyFullbodyRegexes", [r"\bfull\b", r"\bfullbody\b", r"\bfull-body\b", r"\bfb\b"])),
        ),
        BucketRules(
            "halfbody",
            tuple(getCfgValue(cfg, "comfyHalfbodyFolders", ["halfbody", "half-body", "half_body", "half"])),
            tuple(getCfgValue(cfg, "comfyHalfbodyRegexes", [r"\bhalf\b", r"\bhalfbody\b", r"\bhalf-body\b", r"\bhb\b"])),
        ),
        BucketRules(
            "portrait",
            tuple(getCfgValue(cfg, "comfyPortraitFolders", ["portrait", "headshot", "face"])),
            tuple(getCfgValue(cfg, "comfyPortraitRegexes", [r"\bportrait\b", r"\bheadshot\b", r"\bface\b", r"\bhs\b"])),
        ),
    ]

    filenamePrefixTemplate = str(getCfgValue(cfg, "comfyFilenamePrefixTemplate", "fixed_{stem}"))
    downloadPathTemplate = str(getCfgValue(cfg, "comfyDownloadPathTemplate", "{runDir}/{bucket}/{stem}"))

    allImages = [p for p in inputDir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    
    # Apply precedence rules: prefer fixed_* versions over originals
    stemToImage = applyPrecedenceRules(allImages)
    imagesToProcess = list(stemToImage.values())
    
    jobs: List[Tuple[Path, str]] = []
    for img in sorted(imagesToProcess):
        stemSafe = safeStem(img.stem)
        if hasExistingOutput(outputDir=outputDir, fixedPrefix=fixedPrefix, stem=stemSafe):
            relSkip = img.relative_to(inputDir).as_posix()
            logger.info("%s skip (output exists): %s", prefix, relSkip)
            continue
        bucket = classifyImage(img, rules)
        if bucket:
            jobs.append((img, bucket))

    logger.info("%s run dir: %s", prefix, runDir)
    logger.info("%s found images: %d", prefix, len(allImages))
    logger.info("%s unique stems (after precedence): %d", prefix, len(imagesToProcess))
    logger.info("%s matched jobs: %d", prefix, len(jobs))

    if args.limit and args.limit > 0:
        jobs = jobs[: args.limit]
        logger.info("%s limit applied: %d", prefix, len(jobs))

    if not jobs:
        logger.info("%s done.", prefix)
        return 0

    client = ComfyClient(args.comfyurl, args.timeoutseconds)

    for i, (imgPath, bucket) in enumerate(jobs, start=1):
        rel = imgPath.relative_to(inputDir).as_posix()
        stem = safeStem(imgPath.stem)

        wfPath = workflowPaths[bucket]
        prompt = loadApiPromptJson(wfPath)

        loadCount = setLoadImageInput(prompt, rel)
        if loadCount == 0:
            logger.error("No LoadImage node found in workflow: %s", wfPath)
            continue

        prefixValue = renderTemplate(filenamePrefixTemplate, bucket=bucket, stem=stem)
        _ = setSaveImagePrefix(prompt, prefixValue)

        logger.info("%s [%d/%d] %s: %s", prefix, i, len(jobs), bucket, rel)

        if args.dryRun:
            continue

        try:
            promptId = client.submitPrompt(prompt)
            logger.info("%s submitted: %s", prefix, promptId)

            histEntry = client.waitForOutputs(promptId, args.pollseconds, args.maxwaitseconds)
            images = extractOutputImages(histEntry)
            if not images:
                logger.info("%s completed (no outputs)", prefix)
                continue

            dlBase = Path(renderTemplate(downloadPathTemplate, runDir=str(runDir), bucket=bucket, stem=stem))
            dlBase.mkdir(parents=True, exist_ok=True)

            for n, meta in enumerate(images, start=1):
                content = client.downloadView(meta["filename"], meta.get("subfolder", ""), meta.get("type", "output"))
                ext = Path(meta["filename"]).suffix or ".png"
                outFile = dlBase / f"out_{n:02d}{ext}"
                outFile.write_bytes(content)

            logger.info("%s saved outputs: %s", prefix, dlBase)

        except Exception as e:
            logger.error("Failed to process %s: %s", rel, e)

    logger.info("%s done.", prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
