#!/usr/bin/env python3
"""txt2imgComfy.py

Text-to-image runner for ComfyUI (SD1.5) that:
- uses a reference photo to generate prompts (positive + negative) via a LLaVA API
- patches a text2img workflow JSON
- submits to ComfyUI (local or remote)
- downloads outputs and mirrors fixed_* images into comfy output folder

Constraints:
- full-body only (no half-body / portrait classification)
- no img2img (no LoadImage)
- no face detailer, no SAM, no inpainting nodes (workflow should not contain them)

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
import random
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
    """Remove fixed_ prefix and ComfyUI numbering suffixes from a filename stem."""
    stem = Path(filename).stem
    stem = re.sub(r"^fixed_", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"_[0-9]{5}_$", "", stem)  # fixed_xxx_00001_
    stem = re.sub(r"_[0-9]{5}$", "", stem)   # xxx_00001
    return stem


def applyPrecedenceRules(images: List[Path], fixedPrefix: str = "fixed_") -> Dict[str, Path]:
    """Prefer fixed_* versions over originals when both exist for the same base stem."""
    out: Dict[str, Path] = {}
    for p in images:
        baseStem = extractBaseStem(p.name)
        existing = out.get(baseStem)
        if existing is None:
            out[baseStem] = p
            continue

        # If current is fixed_ and existing is not, replace
        if p.name.lower().startswith(fixedPrefix.lower()) and not existing.name.lower().startswith(fixedPrefix.lower()):
            out[baseStem] = p
            continue

        # Otherwise keep existing
    return out


def hasExistingOutput(*, outputDir: Path, fixedPrefix: str, stem: str) -> bool:
    """Check if outputDir already contains any fixed_{stem}_*.png files."""
    pat = f"{fixedPrefix}{stem}_"
    for p in outputDir.glob(f"{pat}*.png"):
        if p.is_file():
            return True
    for p in outputDir.glob(f"{pat}*.jpg"):
        if p.is_file():
            return True
    for p in outputDir.glob(f"{pat}*.webp"):
        if p.is_file():
            return True
    return False


def loadApiPromptJson(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"workflow json is not a dict: {path}")
    return data


def renderTemplate(template: str, **kwargs: str) -> str:
    return template.format(**kwargs)


# ------------------------------------------------------------
# workflow patch helpers (targets your fullbody text2img workflow)
# ------------------------------------------------------------

def setClipText(prompt: Dict[str, Any], *, nodeId: str, text: str) -> None:
    node = prompt.get(nodeId)
    if not isinstance(node, dict):
        raise KeyError(f"missing node id: {nodeId}")
    if node.get("class_type") != "CLIPTextEncode":
        raise ValueError(f"node {nodeId} is not CLIPTextEncode: {node.get('class_type')}")
    node.setdefault("inputs", {})["text"] = text


def setEmptyLatent(prompt: Dict[str, Any], *, nodeId: str, width: int, height: int, batchSize: int) -> None:
    node = prompt.get(nodeId)
    if not isinstance(node, dict):
        raise KeyError(f"missing node id: {nodeId}")
    if node.get("class_type") != "EmptyLatentImage":
        raise ValueError(f"node {nodeId} is not EmptyLatentImage: {node.get('class_type')}")
    inputs = node.setdefault("inputs", {})
    inputs["width"] = int(width)
    inputs["height"] = int(height)
    inputs["batch_size"] = int(batchSize)


def setKSampler(prompt: Dict[str, Any], *, nodeId: str, seed: int, steps: int, cfg: float, sampler: str, scheduler: str) -> None:
    node = prompt.get(nodeId)
    if not isinstance(node, dict):
        raise KeyError(f"missing node id: {nodeId}")
    if node.get("class_type") != "KSampler":
        raise ValueError(f"node {nodeId} is not KSampler: {node.get('class_type')}")
    inputs = node.setdefault("inputs", {})
    inputs["seed"] = int(seed)
    inputs["steps"] = int(steps)
    inputs["cfg"] = float(cfg)
    inputs["sampler_name"] = str(sampler)
    inputs["scheduler"] = str(scheduler)


def setLoraStrength(prompt: Dict[str, Any], *, nodeId: str, strengthModel: float, strengthClip: float) -> None:
    node = prompt.get(nodeId)
    if not isinstance(node, dict):
        raise KeyError(f"missing node id: {nodeId}")
    if node.get("class_type") != "LoraLoader":
        raise ValueError(f"node {nodeId} is not LoraLoader: {node.get('class_type')}")
    inputs = node.setdefault("inputs", {})
    inputs["strength_model"] = float(strengthModel)
    inputs["strength_clip"] = float(strengthClip)


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


# ------------------------------------------------------------
# ComfyUI client (same endpoints/pattern as img2ImgComfy.py)
# ------------------------------------------------------------

class ComfyClient:
    def __init__(self, baseUrl: str, timeoutSeconds: int, *, isRemote: bool):
        self.baseUrl = baseUrl.rstrip("/")
        self.timeoutSeconds = timeoutSeconds
        self.isRemote = isRemote
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


# ------------------------------------------------------------
# Prompt client (LLaVA API)
# ------------------------------------------------------------

@dataclass(frozen=True)
class PromptResult:
    positive: str
    negative: str
    raw: Dict[str, Any]


class PromptClient:
    def __init__(self, baseUrl: str, timeoutSeconds: int):
        self.baseUrl = baseUrl.rstrip("/")
        self.timeoutSeconds = timeoutSeconds
        self.session = requests.Session()

    def analyzeImage(self, imagePath: Path) -> Dict[str, Any]:
        url = self.baseUrl
        with imagePath.open("rb") as f:
            files = {"file": (imagePath.name, f, "image/png")}
            resp = self.session.post(url, files=files, timeout=self.timeoutSeconds)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict):
            raise ValueError("llava api did not return json object")
        return data


def joinParts(parts: List[str]) -> str:
    cleaned = []
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        cleaned.append(p)
    # avoid accidental double commas
    out = ", ".join(cleaned)
    out = re.sub(r"\s*,\s*,\s*", ", ", out)
    return out.strip(" ,")


def buildPromptsFromLlava(
    llavaJson: Dict[str, Any],
    *,
    basePositive: str,
    baseNegative: str,
) -> PromptResult:
    # 1) direct
    if isinstance(llavaJson.get("positivePrompt"), str) and isinstance(llavaJson.get("negativePrompt"), str):
        pos = joinParts([basePositive, llavaJson["positivePrompt"]])
        neg = joinParts([baseNegative, llavaJson["negativePrompt"]])
        return PromptResult(positive=pos, negative=neg, raw=llavaJson)

    # 2) split objects
    posParts: List[str] = []
    negParts: List[str] = []

    positiveParts = llavaJson.get("positiveParts")
    negativeParts = llavaJson.get("negativeParts")
    if isinstance(positiveParts, dict):
        for k in ("pose", "location", "clothing", "lighting", "camera", "composition"):
            v = positiveParts.get(k)
            if isinstance(v, str):
                posParts.append(v)
    if isinstance(negativeParts, dict):
        for k in ("avoid", "negativesHint"):
            v = negativeParts.get(k)
            if isinstance(v, str):
                negParts.append(v)

    # 3) common schema fields
    for k in ("posePrompt", "locationPrompt", "clothingPrompt", "lightingPrompt", "cameraPrompt", "compositionPrompt"):
        v = llavaJson.get(k)
        if isinstance(v, str):
            posParts.append(v)
    v = llavaJson.get("negativesHint")
    if isinstance(v, str):
        negParts.append(v)

    pos = joinParts([basePositive, joinParts(posParts)])
    neg = joinParts([baseNegative, joinParts(negParts)])
    return PromptResult(positive=pos, negative=neg, raw=llavaJson)


# ------------------------------------------------------------
# IO helpers
# ------------------------------------------------------------

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
            mirrorName = f"{fixedPrefix}{stemSafe}_{n:05d}_{ext}"
            mirrorName = mirrorName.replace("__", "_")
            (mirrorDir / mirrorName).write_bytes(content)

    return len(images)


# ------------------------------------------------------------
# args + mode
# ------------------------------------------------------------

def parseArgs(cfg: Dict[str, Any]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ComfyUI text2img workflow using prompts generated from photos (LLaVA).")

    parser.add_argument("--dry-run", dest="dryRun", action="store_true", help="show what would be done without changing anything")
    parser.add_argument("--limit", type=int, default=0, help="process at most N images (0 = no limit)")
    parser.add_argument("--variants", type=int, default=int(getCfgValue(cfg, "comfyText2ImgVariants", 1)), help="images to generate per input (different seeds)")
    parser.add_argument("--seed", type=int, default=int(getCfgValue(cfg, "comfyText2ImgSeed", 0)), help="seed (0 = random per variant)")

    # Mode selection
    parser.add_argument("--local", default=None, help="local ComfyUI base url (e.g. http://127.0.0.1:8188)")
    parser.add_argument("--remote", default=None, help="remote ComfyUI base url (e.g. RunPod proxy url)")

    # Folders (local filesystem)
    parser.add_argument("--comfyin", type=Path, default=Path(getCfgValue(cfg, "comfyInput", "./input")))
    parser.add_argument("--comfyout", type=Path, default=Path(getCfgValue(cfg, "comfyOutput", "./output")))
    parser.add_argument("--workflows", type=Path, default=Path(getCfgValue(cfg, "comfyWorkflowsDir", "./workflows")))
    parser.add_argument("--runsdir", type=Path, default=Path(getCfgValue(cfg, "comfyRunsDir", "./runs")))

    # LLaVA API
    parser.add_argument("--llavaurl", default=str(getCfgValue(cfg, "llavaUrl", "http://127.0.0.1:9000/analyze")))
    parser.add_argument("--llavatimeout", type=int, default=int(getCfgValue(cfg, "llavaTimeoutSeconds", 300)))

    # Workflow + generation overrides
    parser.add_argument("--steps", type=int, default=int(getCfgValue(cfg, "comfyText2ImgSteps", 30)))
    parser.add_argument("--cfg", type=float, default=float(getCfgValue(cfg, "comfyText2ImgCfg", 6.0)))
    parser.add_argument("--sampler", default=str(getCfgValue(cfg, "comfyText2ImgSampler", "dpmpp_2m")))
    parser.add_argument("--scheduler", default=str(getCfgValue(cfg, "comfyText2ImgScheduler", "karras")))
    parser.add_argument("--width", type=int, default=int(getCfgValue(cfg, "comfyText2ImgWidth", 768)))
    parser.add_argument("--height", type=int, default=int(getCfgValue(cfg, "comfyText2ImgHeight", 1024)))
    parser.add_argument("--batch", type=int, default=int(getCfgValue(cfg, "comfyText2ImgBatchSize", 1)))
    parser.add_argument("--loraModel", type=float, default=float(getCfgValue(cfg, "comfyText2ImgLoraStrengthModel", 1.0)))
    parser.add_argument("--loraClip", type=float, default=float(getCfgValue(cfg, "comfyText2ImgLoraStrengthClip", 1.0)))

    # Prompt composition
    parser.add_argument("--basepositive", default=str(getCfgValue(cfg, "comfyText2ImgBasePositive", "")))
    parser.add_argument("--basenegative", default=str(getCfgValue(cfg, "comfyText2ImgBaseNegative", "")))

    # Timing
    parser.add_argument("--timeoutseconds", type=int, default=int(getCfgValue(cfg, "comfyTimeoutSeconds", 120)))
    parser.add_argument("--pollseconds", type=float, default=float(getCfgValue(cfg, "comfyPollSeconds", 1.0)))
    parser.add_argument("--maxwaitseconds", type=int, default=int(getCfgValue(cfg, "comfyMaxWaitSeconds", 1800)))

    # Logging
    parser.add_argument("--loglevel", default=str(getCfgValue(cfg, "comfyLogLevel", "INFO")))
    parser.add_argument("--logconsole", action="store_true", default=bool(getCfgValue(cfg, "comfyLogConsole", True)))

    return parser.parse_args()


def resolveMode(args: argparse.Namespace, cfg: Dict[str, Any]) -> Tuple[str, str]:
    cfgComfyUrl = str(getCfgValue(cfg, "comfyUrl", "")).strip()

    if args.local and args.remote:
        raise ValueError("use either --local OR --remote, not both")

    if args.remote:
        return ("remote", str(args.remote))

    if args.local:
        return ("local", str(args.local))

    if cfgComfyUrl:
        return ("local", cfgComfyUrl)

    raise ValueError("one of --local or --remote is required")


def getWorkflowPath(cfg: Dict[str, Any], workflowsDir: Path) -> Path:
    wfName = str(getCfgValue(cfg, "comfyText2ImgWorkflow", "kathy-text-2-image-api.json"))
    return (workflowsDir / wfName).resolve()


# ------------------------------------------------------------
# main
# ------------------------------------------------------------

def main() -> int:
    cfg = loadConfig()
    args = parseArgs(cfg)

    prefix = "...[]" if args.dryRun else "..."
    logger = getLogger("txt2imgComfy", includeConsole=bool(args.logconsole))
    setLogger(logger)

    try:
        mode, baseUrl = resolveMode(args, cfg)
    except Exception as e:
        logger.error("Invalid arguments: %s", e)
        return 2

    runStamp = time.strftime("%Y%m%d_%H%M%S")
    runDir = Path(args.runsdir).expanduser().resolve() / f"run_{runStamp}"

    updates = {
        "comfyUrl": str(baseUrl),
        "comfyInput": str(Path(args.comfyin).expanduser()),
        "comfyOutput": str(Path(args.comfyout).expanduser()),
        "comfyWorkflowsDir": str(Path(args.workflows).expanduser()),
        "comfyRunsDir": str(Path(args.runsdir).expanduser()),
        "comfyText2ImgWorkflow": str(getCfgValue(cfg, "comfyText2ImgWorkflow", "kathy-text-2-image-api.json")),
        "llavaUrl": str(args.llavaurl),
        "llavaTimeoutSeconds": int(args.llavatimeout),
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
    wfPath = getWorkflowPath(cfg, workflowsDir)
    if not wfPath.exists():
        logger.error("Missing text2img workflow file: %s", wfPath)
        return 2

    comfyInput = Path(args.comfyin).expanduser().resolve()
    if not comfyInput.exists():
        logger.error("Input dir does not exist: %s", comfyInput)
        return 2

    comfyOutput = Path(args.comfyout).expanduser().resolve()
    comfyOutput.mkdir(parents=True, exist_ok=True)

    fixedPrefix = str(getCfgValue(cfg, "comfyFixedOutputPrefix", "fixed_"))
    filenamePrefixTemplate = str(getCfgValue(cfg, "comfyFilenamePrefixTemplate", "fixed_{stem}"))
    downloadPathTemplate = str(getCfgValue(cfg, "comfyDownloadPathTemplate", "{runDir}/{bucket}/{stem}"))

    # full-body only
    bucket = "fullbody"

    allImages = [p for p in comfyInput.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
    stemToImage = applyPrecedenceRules(allImages, fixedPrefix=fixedPrefix)
    imagesToProcess = list(stemToImage.values())

    jobs: List[Path] = []
    for img in sorted(imagesToProcess):
        stemSafe = safeStem(img.stem)
        if hasExistingOutput(outputDir=comfyOutput, fixedPrefix=fixedPrefix, stem=stemSafe):
            relSkip = img.relative_to(comfyInput).as_posix()
            logger.info("%s skip (output exists): %s", prefix, relSkip)
            continue
        jobs.append(img)

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

    client = ComfyClient(baseUrl, args.timeoutseconds, isRemote=(mode == "remote"))
    promptClient = PromptClient(args.llavaurl, args.llavatimeout)

    for i, imgPath in enumerate(jobs, start=1):
        rel = imgPath.relative_to(comfyInput).as_posix()
        stemSafe = safeStem(imgPath.stem)

        logger.info("%s [%d/%d] prompting: %s", prefix, i, len(jobs), rel)

        if args.dryRun:
            llavaJson = {}
            promptRes = PromptResult(positive=args.basepositive, negative=args.basenegative, raw=llavaJson)
        else:
            try:
                llavaJson = promptClient.analyzeImage(imgPath)
                promptRes = buildPromptsFromLlava(
                    llavaJson,
                    basePositive=str(args.basepositive),
                    baseNegative=str(args.basenegative),
                )
            except Exception as e:
                logger.error("Failed to generate prompt for %s: %s", rel, e)
                continue

        # Generate variants (different seeds)
        variants = max(1, int(args.variants))
        for v in range(1, variants + 1):
            prompt = loadApiPromptJson(wfPath)

            # Patch workflow using your known node ids:
            # 2 = LoraLoader, 3 = positive, 4 = negative, 5 = EmptyLatentImage, 6 = KSampler, 8 = SaveImage
            try:
                setClipText(prompt, nodeId="3", text=promptRes.positive)
                setClipText(prompt, nodeId="4", text=promptRes.negative)

                setEmptyLatent(prompt, nodeId="5", width=args.width, height=args.height, batchSize=args.batch)

                seed = int(args.seed)
                if seed == 0:
                    seed = random.randint(1, 2**31 - 1)
                else:
                    # deterministic per variant
                    seed = seed + (v - 1)

                setKSampler(
                    prompt,
                    nodeId="6",
                    seed=seed,
                    steps=args.steps,
                    cfg=args.cfg,
                    sampler=args.sampler,
                    scheduler=args.scheduler,
                )

                setLoraStrength(prompt, nodeId="2", strengthModel=args.loraModel, strengthClip=args.loraClip)

                # prefix includes variant to avoid overwriting
                prefixValue = renderTemplate(filenamePrefixTemplate, stem=f"{stemSafe}_t2i_v{v:02d}")
                _ = setSaveImagePrefix(prompt, prefixValue)

            except Exception as e:
                logger.error("Failed to patch workflow for %s: %s", rel, e)
                continue

            logger.info(
                "%s [%d/%d] generating (%s v%02d): %s",
                prefix,
                i,
                len(jobs),
                bucket,
                v,
                rel,
            )

            if args.dryRun:
                continue

            try:
                promptId = client.submitPrompt(prompt)
                logger.info("%s submitted: %s", prefix, promptId)

                histEntry = client.waitForOutputs(promptId, args.pollseconds, args.maxwaitseconds)

                dlBase = Path(
                    renderTemplate(
                        downloadPathTemplate,
                        runDir=str(runDir),
                        bucket=bucket,
                        stem=f"{stemSafe}/v{v:02d}",
                    )
                )

                mirrorDir = comfyOutput
                nOut = writeOutputs(
                    client=client,
                    historyEntry=histEntry,
                    dlBase=dlBase,
                    mirrorDir=mirrorDir,
                    fixedPrefix=fixedPrefix,
                    stemSafe=f"{stemSafe}_t2i_v{v:02d}",
                    dryRun=args.dryRun,
                )

                if nOut == 0:
                    logger.info("%s completed (no outputs)", prefix)
                else:
                    logger.info("%s saved outputs: %s", prefix, dlBase)

            except Exception as e:
                logger.error("Failed to generate %s: %s", rel, e)

    logger.info("%s done.", prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
