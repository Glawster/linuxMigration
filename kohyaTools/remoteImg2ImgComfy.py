#!/usr/bin/env python3
"""
remoteImg2ImgComfy.py

Run ComfyUI img2img workflows on a *remote* ComfyUI (e.g. RunPod proxy),
while keeping all files local.

Flow per image:
- upload local image -> remote ComfyUI /input (optionally under a subfolder)
- POST /prompt with workflow (LoadImage points to uploaded file)
- poll /history/{prompt_id}
- download outputs via /view
- save outputs to local runs dir (and optionally mirror into local "comfyOutput")

Conventions:
- uses ~/.config/kohya/kohyaConfig.json via kohyaConfig.py (no --configPath)
- logging via organiseMyProjects.logUtils.getLogger
- --dry-run: no side effects (no network calls, no file writes), but logs same messages
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


class ComfyClient:
    def __init__(self, baseUrl: str, timeoutSeconds: int):
        self.baseUrl = baseUrl.rstrip("/")
        self.timeoutSeconds = timeoutSeconds
        self.session = requests.Session()

    def uploadImage(self, localPath: Path, remoteName: str, subfolder: str, overwrite: bool) -> str:
        """
        Upload an image to the remote ComfyUI input directory via /upload/image.

        Returns the image name/path you should set into LoadImage:
          - if subfolder empty -> remoteName
          - else -> f"{subfolder}/{remoteName}"
        """
        url = f"{self.baseUrl}/upload/image"

        # ComfyUI expects multipart/form-data with field name "image"
        # Common optional fields: subfolder, overwrite
        data = {
            "subfolder": subfolder or "",
            "overwrite": "true" if overwrite else "false",
        }

        mime = "image/png"
        if localPath.suffix.lower() in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif localPath.suffix.lower() == ".webp":
            mime = "image/webp"

        with localPath.open("rb") as f:
            files = {"image": (remoteName, f, mime)}
            resp = self.session.post(url, data=data, files=files, timeout=self.timeoutSeconds)
        resp.raise_for_status()

        # Most servers return JSON; we don't rely on exact schema, just success.
        remoteRef = remoteName if not subfolder else f"{subfolder}/{remoteName}"
        return remoteRef

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


def parseArgs(cfg: Dict[str, Any]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run img2img workflows on remote ComfyUI (RunPod) while keeping files local.")

    parser.add_argument("--confirm", action="store_true", help="execute changes (default is dry-run mode)")
    parser.add_argument("--limit", type=int, default=0, help="process at most N images (0 = no limit)")

    # Remote ComfyUI base URL: e.g. https://PODID-8188.proxy.runpod.net
    parser.add_argument("--comfyurl", default=getCfgValue(cfg, "comfyUrl", "http://127.0.0.1:8188"))

    # Local folders
    parser.add_argument("--localin", type=Path, default=Path(getCfgValue(cfg, "comfyInput", "./input")))
    parser.add_argument("--localout", type=Path, default=Path(getCfgValue(cfg, "comfyOutput", "./output")))
    parser.add_argument("--workflows", type=Path, default=Path(getCfgValue(cfg, "comfyWorkflowsDir", "./workflows")))
    parser.add_argument("--runsdir", type=Path, default=Path(getCfgValue(cfg, "comfyRunsDir", "./runs")))

    # Remote upload options
    parser.add_argument("--remotesubfolder", default=str(getCfgValue(cfg, "comfyRemoteUploadSubfolder", "remoteImg2ImgComfy")))
    parser.add_argument("--remoteoverwrite", action="store_true", default=bool(getCfgValue(cfg, "comfyRemoteUploadOverwrite", True)))

    # Timing
    parser.add_argument("--timeoutseconds", type=int, default=int(getCfgValue(cfg, "comfyTimeoutSeconds", 120)))
    parser.add_argument("--pollseconds", type=float, default=float(getCfgValue(cfg, "comfyPollSeconds", 1.0)))
    parser.add_argument("--maxwaitseconds", type=int, default=int(getCfgValue(cfg, "comfyMaxWaitSeconds", 1800)))

    # Logging
    parser.add_argument("--loglevel", default=str(getCfgValue(cfg, "comfyLogLevel", "INFO")))
    parser.add_argument("--logconsole", action="store_true", default=bool(getCfgValue(cfg, "comfyLogConsole", True)))

    return parser.parse_args()


def main() -> int:
    cfg = loadConfig()
    args = parseArgs(cfg)
    args.dryRun = not args.confirm

    prefix = "...[]" if args.dryRun else "..."
    logger = getLogger("remoteImg2ImgComfy", includeConsole=bool(args.logconsole))

    runStamp = time.strftime("%Y%m%d_%H%M%S")
    runDir = Path(args.runsdir).expanduser().resolve() / f"run_{runStamp}"

    updates = {
        "comfyUrl": str(args.comfyurl),
        "comfyInput": str(Path(args.localin).expanduser()),
        "comfyOutput": str(Path(args.localout).expanduser()),
        "comfyWorkflowsDir": str(Path(args.workflows).expanduser()),
        "comfyRunsDir": str(Path(args.runsdir).expanduser()),
        "comfyRemoteUploadSubfolder": str(args.remotesubfolder),
        "comfyRemoteUploadOverwrite": bool(args.remoteoverwrite),
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

    # Workflows
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

    localIn = Path(args.localin).expanduser().resolve()
    if not localIn.exists():
        logger.error("Input dir does not exist: %s", localIn)
        return 2

    localOut = Path(args.localout).expanduser().resolve()
    localOut.mkdir(parents=True, exist_ok=True)

    fixedPrefix = str(getCfgValue(cfg, "comfyFixedOutputPrefix", "fixed_"))
    filenamePrefixTemplate = str(getCfgValue(cfg, "comfyFilenamePrefixTemplate", "fixed_{stem}"))
    downloadPathTemplate = str(getCfgValue(cfg, "comfyDownloadPathTemplate", "{runDir}/{bucket}/{stem}"))

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

    allImages = [p for p in localIn.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]

    jobs: List[Tuple[Path, str]] = []
    for img in sorted(allImages):
        bucket = classifyImage(img, rules)
        if bucket:
            jobs.append((img, bucket))

    logger.info("%s run dir: %s", prefix, runDir)
    logger.info("%s found images: %d", prefix, len(allImages))
    logger.info("%s matched jobs: %d", prefix, len(jobs))

    if args.limit and args.limit > 0:
        jobs = jobs[: args.limit]
        logger.info("%s limit applied: %d", prefix, len(jobs))

    if not jobs:
        logger.info("%s done.", prefix)
        return 0

    client = ComfyClient(args.comfyurl, args.timeoutseconds)

    # Make remote uploads unique per run to avoid collisions
    remoteSubfolder = f"{args.remotesubfolder}/{runStamp}"

    for i, (imgPath, bucket) in enumerate(jobs, start=1):
        relLocal = imgPath.relative_to(localIn).as_posix()
        stemSafe = safeStem(imgPath.stem)

        wfPath = workflowPaths[bucket]
        prompt = loadApiPromptJson(wfPath)

        # Upload
        remoteName = f"{stemSafe}{imgPath.suffix.lower()}"
        logger.info("%s [%d/%d] upload %s: %s", prefix, i, len(jobs), bucket, relLocal)

        if args.dryRun:
            continue

        try:
            remoteRef = client.uploadImage(
                localPath=imgPath,
                remoteName=remoteName,
                subfolder=remoteSubfolder,
                overwrite=bool(args.remoteoverwrite),
            )

            # Point workflow LoadImage to the uploaded path
            loadCount = setLoadImageInput(prompt, remoteRef)
            if loadCount == 0:
                logger.error("No LoadImage node found in workflow: %s", wfPath)
                continue

            prefixValue = renderTemplate(filenamePrefixTemplate, bucket=bucket, stem=stemSafe)
            _ = setSaveImagePrefix(prompt, prefixValue)

            logger.info("%s [%d/%d] run %s: %s", prefix, i, len(jobs), bucket, relLocal)

            promptId = client.submitPrompt(prompt)
            logger.info("%s submitted: %s", prefix, promptId)

            histEntry = client.waitForOutputs(promptId, args.pollseconds, args.maxwaitseconds)
            images = extractOutputImages(histEntry)
            if not images:
                logger.info("%s completed (no outputs): %s", prefix, relLocal)
                continue

            # Save outputs locally (runs dir + optionally also mirror to localOut)
            dlBase = Path(renderTemplate(downloadPathTemplate, runDir=str(runDir), bucket=bucket, stem=stemSafe))
            dlBase.mkdir(parents=True, exist_ok=True)

            for n, meta in enumerate(images, start=1):
                content = client.downloadView(meta["filename"], meta.get("subfolder", ""), meta.get("type", "output"))
                ext = Path(meta["filename"]).suffix or ".png"

                outFile = dlBase / f"out_{n:02d}{ext}"
                outFile.write_bytes(content)

                # Mirror: write a "fixed_" file into localOut for downstream scripts
                # Keep ComfyUI-ish naming simple: fixed_<stem>_00001_.png, etc.
                mirrorName = f"{fixedPrefix}{stemSafe}_{n:05d}_{ext}"
                mirrorName = mirrorName.replace("__", "_")
                mirrorPath = localOut / mirrorName
                mirrorPath.write_bytes(content)

            logger.info("%s saved outputs: %s", prefix, dlBase)

        except Exception as e:
            logger.error("Failed to process %s: %s", relLocal, e)

    logger.info("%s done.", prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
