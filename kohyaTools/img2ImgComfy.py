#!/usr/bin/env python3
"""img2ImgComfy.py

Unified runner for ComfyUI img2img workflows using the fullbody workflow for all images.

Modes:
- Local mode:   use --comfyurl (e.g. http://127.0.0.1:8188)
- Remote mode:  use --remoteurl (e.g. https://<pod>-8188.proxy.runpod.net)

Selection rules:
- Provide exactly one of --comfyurl or --remoteurl.

Workflow:
- Uses only the fullbody workflow (comfyFullbodyWorkflow in config) for all images.
- No classification needed - processes all images found.

Local mode behaviour:
- Looks for images under --comfyin (ComfyUI input folder).
- For each unique image stem, prefers processed (fixed_*) images over originals.
- Skips images that already have a fixed_* output in --comfyout.
- Submits workflows with LoadImage pointing at the *relative* path under --comfyin.
- Downloads outputs into --runsdir/run_<stamp>/...

Remote mode behaviour (RunPod etc.):
- Keeps files local, uploads each image to remote ComfyUI /input via /upload/image.
- Submits workflow with LoadImage pointing at the uploaded file.
- Downloads outputs via /view.
- Saves outputs into --runsdir/run_<stamp>/... and mirrors fixed_* files into --comfyout
  for downstream scripts.

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
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from kohyaConfig import (  # type: ignore
    DEFAULT_CONFIG_PATH,
    getCfgValue,
    loadConfig,
    saveConfig,
    setLogger,
    updateConfigFromArgs,
)
from organiseMyProjects.logUtils import getLogger  # type: ignore


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def safeStem(stem: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", stem).strip("_") or "image"


def extractBaseStem(filename: str) -> str:
    """Extract the base stem, removing fixed_ prefix and ComfyUI numbering.

    Examples:
        fixed_photo-01_00001_.png -> photo-01
        photo-01.png -> photo-01
        fixed_style-name-01_00002_.png -> style-name-01
    """
    stem = Path(filename).stem
    if stem.lower().startswith("fixed_"):
        stem = stem[6:]
    stem = re.sub(r"_\d+_$", "", stem)
    return stem


def applyPrecedenceRules(allImages: List[Path]) -> Dict[str, Path]:
    """Prefer fixed_* versions over originals per base stem.

    Returns a dict mapping base stem -> chosen image path.
    """
    stemToImages: Dict[str, List[Path]] = {}

    for img in allImages:
        baseStem = extractBaseStem(img.name)
        stemToImages.setdefault(baseStem, []).append(img)

    result: Dict[str, Path] = {}
    for baseStem, images in stemToImages.items():
        fixedVersions = [img for img in images if img.name.lower().startswith("fixed_")]
        originals = [img for img in images if not img.name.lower().startswith("fixed_")]

        if fixedVersions:
            # If multiple, take the last by sort (often newest by numbering/path).
            result[baseStem] = sorted(fixedVersions)[-1]
        elif originals:
            result[baseStem] = sorted(originals)[0]

    return result


def hasExistingOutput(outputDir: Path, fixedPrefix: str, stem: str) -> bool:
    """True if outputDir already contains fixedPrefix+stem.* (any suffix/counter)."""
    if not outputDir.exists() or not outputDir.is_dir():
        return False

    prefix = f"{fixedPrefix}{stem}"
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


class ComfyClient:
    def __init__(self, baseUrl: str, timeoutSeconds: int, *, isRemote: bool):
        self.baseUrl = baseUrl.rstrip("/")
        self.timeoutSeconds = timeoutSeconds
        self.isRemote = isRemote
        self.session = requests.Session()

    def uploadImage(self, localPath: Path, remoteName: str, subfolder: str, overwrite: bool) -> str:
        """Upload image to remote ComfyUI /input via /upload/image.

        Returns the string to set into LoadImage.
        """
        if not self.isRemote:
            raise RuntimeError("uploadImage called in local mode")

        url = f"{self.baseUrl}/upload/image"
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

        return remoteName if not subfolder else f"{subfolder}/{remoteName}"

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
    parser = argparse.ArgumentParser(description="Run ComfyUI img2img workflows locally or remotely (RunPod).")

    parser.add_argument("--dry-run", dest="dryRun", action="store_true", help="show what would be done without changing anything")
    parser.add_argument("--limit", type=int, default=0, help="process at most N images (0 = no limit)")

    # Mode selection
    parser.add_argument("--comfyurl", default=None, help="local ComfyUI base url (e.g. http://127.0.0.1:8188)")
    parser.add_argument("--remoteurl", default=None, help="remote ComfyUI base url (e.g. RunPod proxy url)")

    # Folders (local filesystem)
    parser.add_argument("--comfyin", type=Path, default=Path(getCfgValue(cfg, "comfyInput", "./input")))
    parser.add_argument("--comfyout", type=Path, default=Path(getCfgValue(cfg, "comfyOutput", "./output")))
    parser.add_argument("--workflows", type=Path, default=Path(getCfgValue(cfg, "comfyWorkflowsDir", "./workflows")))
    parser.add_argument("--runsdir", type=Path, default=Path(getCfgValue(cfg, "comfyRunsDir", "./runs")))

    # Remote upload options (used only in remote mode)
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


def resolveMode(args: argparse.Namespace, cfg: Dict[str, Any]) -> Tuple[str, str]:
    """Return (mode, baseUrl)."""

    # Backward compatible: if user didn't pass --comfyurl/--remoteurl, fall back to config comfyUrl as local.
    # But still require explicit intent if neither is provided AND cfg has no comfyUrl.
    cfgComfyUrl = str(getCfgValue(cfg, "comfyUrl", "")).strip()

    if args.comfyurl and args.remoteurl:
        raise ValueError("use either --comfyurl OR --remoteurl, not both")

    if args.remoteurl:
        return ("remote", str(args.remoteurl))

    if args.comfyurl:
        return ("local", str(args.comfyurl))

    if cfgComfyUrl:
        return ("local", cfgComfyUrl)

    raise ValueError("one of --comfyurl or --remoteurl is required")


def getWorkflowPath(cfg: Dict[str, Any], workflowsDir: Path) -> Path:
    """Get the fullbody workflow path (only workflow used)."""
    fullWf = workflowsDir / getCfgValue(cfg, "comfyFullbodyWorkflow", "fullbody_api.json")
    return fullWf.resolve()


def writeOutputs(
    *,
    client: ComfyClient,
    historyEntry: Dict[str, Any],
    dlBase: Path,
    mirrorDir: Optional[Path],
    fixedPrefix: str,
    stemSafe: str,
    dryRun: bool,
) -> int:
    images = extractOutputImages(historyEntry)
    if not images:
        return 0

    if dryRun:
        return len(images)

    dlBase.mkdir(parents=True, exist_ok=True)

    for n, meta in enumerate(images, start=1):
        content = client.downloadView(meta["filename"], meta.get("subfolder", ""), meta.get("type", "output"))
        ext = Path(meta["filename"]).suffix or ".png"

        outFile = dlBase / f"out_{n:02d}{ext}"
        outFile.write_bytes(content)

        if mirrorDir is not None:
            mirrorDir.mkdir(parents=True, exist_ok=True)
            # fixed_<stem>_00001_.png
            extNoDot = ext.lstrip(".")
            mirrorName = f"{fixedPrefix}{stemSafe}_{n:05d}_.{extNoDot}"
            (mirrorDir / mirrorName).write_bytes(content)

    return len(images)


def main() -> int:
    cfg = loadConfig()
    args = parseArgs(cfg)

    prefix = "...[]" if args.dryRun else "..."
    logger = getLogger("img2ImgComfy", includeConsole=bool(args.logconsole))
    setLogger(logger)

    try:
        mode, baseUrl = resolveMode(args, cfg)
    except Exception as e:
        logger.error("Invalid arguments: %s", e)
        return 2

    runStamp = time.strftime("%Y%m%d_%H%M%S")
    runDir = Path(args.runsdir).expanduser().resolve() / f"run_{runStamp}"

    # Persist config (same keys used by both scripts)
    updates = {
        "comfyUrl": str(baseUrl),
        "comfyInput": str(Path(args.comfyin).expanduser()),
        "comfyOutput": str(Path(args.comfyout).expanduser()),
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

    logger.info("%s mode: %s", prefix, mode)
    logger.info("%s base url: %s", prefix, baseUrl)

    workflowsDir = Path(args.workflows).expanduser().resolve()
    workflowPath = getWorkflowPath(cfg, workflowsDir)
    if not workflowPath.exists():
        logger.error("Missing workflow file: %s", workflowPath)
        return 2

    comfyInput = Path(args.comfyin).expanduser().resolve()
    if not comfyInput.exists():
        logger.error("Input dir does not exist: %s", comfyInput)
        return 2

    comfyOutput = Path(args.comfyout).expanduser().resolve()
    comfyOutput.mkdir(parents=True, exist_ok=True)

    fixedPrefix = str(getCfgValue(cfg, "comfyFixedOutputPrefix", "fixed_"))
    filenamePrefixTemplate = str(getCfgValue(cfg, "comfyFilenamePrefixTemplate", "fixed_{stem}"))
    downloadPathTemplate = str(getCfgValue(cfg, "comfyDownloadPathTemplate", "{runDir}/{stem}"))

    allImages = [p for p in comfyInput.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]

    # Precedence rules: prefer fixed_ versions when present
    stemToImage = applyPrecedenceRules(allImages)
    imagesToProcess = list(stemToImage.values())

    jobs: List[Path] = []
    for img in sorted(imagesToProcess):
        stemSafe = safeStem(img.stem)

        # Skip if already processed
        if hasExistingOutput(outputDir=comfyOutput, fixedPrefix=fixedPrefix, stem=stemSafe):
            relSkip = img.relative_to(comfyInput).as_posix()
            logger.info("%s skip (output exists): %s", prefix, relSkip)
            continue

        jobs.append(img)

    logger.info("%s run dir: %s", prefix, runDir)
    logger.info("%s found images: %d", prefix, len(allImages))
    logger.info("%s unique stems (after precedence): %d", prefix, len(imagesToProcess))
    logger.info("%s jobs to process: %d", prefix, len(jobs))

    if args.limit and args.limit > 0:
        jobs = jobs[: args.limit]
        logger.info("%s limit applied: %d", prefix, len(jobs))

    if not jobs:
        logger.info("%s done.", prefix)
        return 0

    client = ComfyClient(baseUrl, args.timeoutseconds, isRemote=(mode == "remote"))

    # For remote mode, make uploads unique per run
    remoteSubfolder = f"{args.remotesubfolder}/{runStamp}" if mode == "remote" else ""

    for i, imgPath in enumerate(jobs, start=1):
        rel = imgPath.relative_to(comfyInput).as_posix()
        stemSafe = safeStem(imgPath.stem)

        prompt = loadApiPromptJson(workflowPath)

        # Prepare LoadImage reference
        if mode == "local":
            loadRef = rel
        else:
            remoteName = f"{stemSafe}{imgPath.suffix.lower()}"
            logger.info("%s [%d/%d] upload: %s", prefix, i, len(jobs), rel)
            if args.dryRun:
                loadRef = f"{remoteSubfolder}/{remoteName}" if remoteSubfolder else remoteName
            else:
                try:
                    loadRef = client.uploadImage(
                        localPath=imgPath,
                        remoteName=remoteName,
                        subfolder=remoteSubfolder,
                        overwrite=bool(args.remoteoverwrite),
                    )
                except Exception as e:
                    logger.error("Failed to upload %s: %s", rel, e)
                    continue

        loadCount = setLoadImageInput(prompt, loadRef)
        if loadCount == 0:
            logger.error("No LoadImage node found in workflow: %s", workflowPath)
            continue

        prefixValue = renderTemplate(filenamePrefixTemplate, stem=stemSafe)
        _ = setSaveImagePrefix(prompt, prefixValue)

        logger.info("%s [%d/%d] processing: %s", prefix, i, len(jobs), rel)

        if args.dryRun:
            continue

        try:
            promptId = client.submitPrompt(prompt)
            logger.info("%s submitted: %s", prefix, promptId)

            histEntry = client.waitForOutputs(promptId, args.pollseconds, args.maxwaitseconds)

            dlBase = Path(renderTemplate(downloadPathTemplate, runDir=str(runDir), stem=stemSafe))

            mirrorDir = comfyOutput if mode == "remote" else None
            nOut = writeOutputs(
                client=client,
                historyEntry=histEntry,
                dlBase=dlBase,
                mirrorDir=mirrorDir,
                fixedPrefix=fixedPrefix,
                stemSafe=stemSafe,
                dryRun=args.dryRun,
            )

            if nOut == 0:
                logger.info("%s completed (no outputs)", prefix)
            else:
                logger.info("%s saved outputs: %s", prefix, dlBase)

        except Exception as e:
            logger.error("Failed to process %s: %s", rel, e)

    logger.info("%s done.", prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
