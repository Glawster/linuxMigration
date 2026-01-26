#!/usr/bin/env python3
"""
txt2imgComfy.py

Run a ComfyUI *text2img* workflow using pre-generated prompt sidecars.

Design goals:
- Minimal CLI: you only pass what you actually use.
- Everything else comes from kohyaConfig.json.
- NO prompt generation here.
- If an image has no .prompt.json sidecar -> log + skip.
- Full-body only (single workflow).

Required sidecar format (minimum):
{
  "assembled": {
    "positive": "...",
    "negative": "..."
  }
}
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from kohyaConfig import (  # type: ignore
    loadConfig,
    getCfgValue,
    setLogger,
)
from organiseMyProjects.logUtils import getLogger  # type: ignore


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


# ------------------------------------------------------------
# helpers
# ------------------------------------------------------------

def safeStem(stem: str) -> str:
    out = []
    for c in stem:
        out.append(c if (c.isalnum() or c in "._-") else "_")
    s = "".join(out).strip("_")
    return s or "image"


def loadPromptSidecar(imgPath: Path) -> Optional[Dict[str, Any]]:
    sidecar = imgPath.with_suffix(".prompt.json")
    if not sidecar.exists():
        return None
    with sidecar.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return None
    return data


def loadWorkflow(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"workflow json is not an object: {path}")
    return data


def ensureDir(path: Path, dryRun: bool) -> None:
    if dryRun:
        return
    path.mkdir(parents=True, exist_ok=True)


# ------------------------------------------------------------
# workflow patch helpers (node IDs fixed to your workflow)
# Your kathy-text-2-image-api.json uses:
# 2=LoraLoader, 3=positive CLIPTextEncode, 4=negative CLIPTextEncode,
# 5=EmptyLatentImage, 6=KSampler, 8=SaveImage
# ------------------------------------------------------------

def setClipText(prompt: Dict[str, Any], nodeId: str, text: str) -> None:
    node = prompt[nodeId]
    node["inputs"]["text"] = text


def setEmptyLatent(prompt: Dict[str, Any], nodeId: str, w: int, h: int, batch: int) -> None:
    node = prompt[nodeId]
    node["inputs"]["width"] = int(w)
    node["inputs"]["height"] = int(h)
    node["inputs"]["batch_size"] = int(batch)


def setKSampler(
    prompt: Dict[str, Any],
    nodeId: str,
    *,
    seed: int,
    steps: int,
    cfg: float,
    sampler: str,
    scheduler: str,
) -> None:
    node = prompt[nodeId]
    node["inputs"]["seed"] = int(seed)
    node["inputs"]["steps"] = int(steps)
    node["inputs"]["cfg"] = float(cfg)
    node["inputs"]["sampler_name"] = str(sampler)
    node["inputs"]["scheduler"] = str(scheduler)


def setLoraStrength(prompt: Dict[str, Any], nodeId: str, model: float, clip: float) -> None:
    node = prompt[nodeId]
    node["inputs"]["strength_model"] = float(model)
    node["inputs"]["strength_clip"] = float(clip)


def setSavePrefix(prompt: Dict[str, Any], prefix: str) -> None:
    for node in prompt.values():
        if isinstance(node, dict) and node.get("class_type") == "SaveImage":
            node.setdefault("inputs", {})["filename_prefix"] = prefix


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
# ComfyUI client
# ------------------------------------------------------------

class ComfyClient:
    def __init__(self, baseUrl: str, timeout: int):
        self.baseUrl = baseUrl.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def submit(self, workflow: Dict[str, Any]) -> str:
        r = self.session.post(
            f"{self.baseUrl}/prompt",
            json={"prompt": workflow},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        pid = data.get("prompt_id")
        if not pid:
            raise RuntimeError(f"no prompt_id in response: {data}")
        return pid

    def wait(self, promptId: str, poll: float, maxWait: int) -> Dict[str, Any]:
        start = time.time()
        while True:
            r = self.session.get(
                f"{self.baseUrl}/history/{promptId}",
                timeout=self.timeout,
            )
            r.raise_for_status()
            hist = r.json()
            if promptId in hist:
                entry = hist[promptId]
                if isinstance(entry, dict) and entry.get("outputs"):
                    return entry
            if time.time() - start > maxWait:
                raise TimeoutError(f"timed out waiting for prompt: {promptId}")
            time.sleep(poll)

    def download(self, filename: str, subfolder: str, kind: str) -> bytes:
        r = self.session.get(
            f"{self.baseUrl}/view",
            params={"filename": filename, "subfolder": subfolder, "type": kind},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.content


# ------------------------------------------------------------
# args (MINIMAL)
# ------------------------------------------------------------

def parseArgs() -> argparse.Namespace:
    p = argparse.ArgumentParser("Run text2img via ComfyUI using .prompt.json sidecars (full-body only)")

    p.add_argument("--dry-run", action="store_true", help="log what would happen (no network, no file writes)")
    p.add_argument("--limit", type=int, default=0, help="process at most N images (0 = all)")
    p.add_argument("--variants", type=int, default=1, help="generate N variants per input image")

    p.add_argument("--local", default=None, help="ComfyUI base url (e.g. http://127.0.0.1:8188)")
    p.add_argument("--remote", default=None, help="ComfyUI base url (e.g. RunPod proxy url)")

    return p.parse_args()


def resolveBaseUrl(args: argparse.Namespace, cfg: Dict[str, Any]) -> str:
    if args.local and args.remote:
        raise ValueError("use --local OR --remote, not both")

    if args.remote:
        return str(args.remote).strip()

    if args.local:
        return str(args.local).strip()

    cfgUrl = str(getCfgValue(cfg, "comfyUrl", "")).strip()
    if not cfgUrl:
        raise ValueError("no ComfyUI url. set comfyUrl in config or pass --local/--remote")
    return cfgUrl


# ------------------------------------------------------------
# main
# ------------------------------------------------------------

def main() -> int:
    cfg = loadConfig()
    args = parseArgs()

    prefix = "...[]" if args.dry_run else "..."
    logger = getLogger("txt2imgComfy", includeConsole=True)
    setLogger(logger)

    try:
        baseUrl = resolveBaseUrl(args, cfg)
    except Exception as e:
        logger.error("Invalid arguments: %s", e)
        return 2

    # config-only settings
    comfyInput = Path(getCfgValue(cfg, "comfyInput", "./input")).expanduser().resolve()
    comfyOutput = Path(getCfgValue(cfg, "comfyOutput", "./output")).expanduser().resolve()
    workflowsDir = Path(getCfgValue(cfg, "comfyWorkflowsDir", "./workflows")).expanduser().resolve()
    runsDir = Path(getCfgValue(cfg, "comfyRunsDir", "./runs")).expanduser().resolve()

    wfName = str(getCfgValue(cfg, "comfyText2ImgWorkflow", "kathy-text-2-image-api.json"))
    wfPath = (workflowsDir / wfName).resolve()

    steps = int(getCfgValue(cfg, "comfyText2ImgSteps", 30))
    cfgScale = float(getCfgValue(cfg, "comfyText2ImgCfg", 6.0))
    sampler = str(getCfgValue(cfg, "comfyText2ImgSampler", "dpmpp_2m"))
    scheduler = str(getCfgValue(cfg, "comfyText2ImgScheduler", "karras"))
    width = int(getCfgValue(cfg, "comfyText2ImgWidth", 768))
    height = int(getCfgValue(cfg, "comfyText2ImgHeight", 1024))
    batchSize = int(getCfgValue(cfg, "comfyText2ImgBatchSize", 1))
    loraModel = float(getCfgValue(cfg, "comfyText2ImgLoraStrengthModel", 1.0))
    loraClip = float(getCfgValue(cfg, "comfyText2ImgLoraStrengthClip", 1.0))

    timeoutSeconds = int(getCfgValue(cfg, "comfyTimeoutSeconds", 120))
    pollSeconds = float(getCfgValue(cfg, "comfyPollSeconds", 1.0))
    maxWaitSeconds = int(getCfgValue(cfg, "comfyMaxWaitSeconds", 1800))

    fixedPrefix = str(getCfgValue(cfg, "comfyFixedOutputPrefix", "fixed_"))
    # Default: fixed_{stem}_t2i_v{variant}
    prefixTemplate = str(getCfgValue(cfg, "comfyText2ImgFilenamePrefixTemplate", "{fixed}{stem}_t2i_v{v:02d}"))

    # basic validation
    if not comfyInput.exists():
        logger.error("Input dir does not exist: %s", comfyInput)
        return 2
    if not wfPath.exists():
        logger.error("Missing workflow file: %s", wfPath)
        return 2

    # dirs
    runStamp = time.strftime("%Y%m%d_%H%M%S")
    runDir = runsDir / f"run_{runStamp}"

    logger.info("%s base url: %s", prefix, baseUrl)
    logger.info("%s workflow: %s", prefix, wfPath)
    logger.info("%s input: %s", prefix, comfyInput)
    logger.info("%s output: %s", prefix, comfyOutput)
    logger.info("%s runs: %s", prefix, runDir)
    logger.info("%s gen params: %dx%d steps=%d cfg=%.2f sampler=%s scheduler=%s batch=%d lora=(%.2f,%.2f)",
                prefix, width, height, steps, cfgScale, sampler, scheduler, batchSize, loraModel, loraClip)
    logger.info("%s variants: %d", prefix, max(1, int(args.variants)))
    if args.limit and args.limit > 0:
        logger.info("%s limit: %d", prefix, args.limit)

    ensureDir(runDir, args.dry_run)
    ensureDir(comfyOutput, args.dry_run)

    # gather images (full-body only; we still take any images present)
    images: List[Path] = [
        p for p in comfyInput.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    images.sort()

    if args.limit and args.limit > 0:
        images = images[: args.limit]

    logger.info("%s found images: %d", prefix, len(images))

    if args.dry_run:
        client = None
    else:
        client = ComfyClient(baseUrl, timeoutSeconds)

    for idx, img in enumerate(images, start=1):
        rel = img.relative_to(comfyInput).as_posix()
        stem = safeStem(img.stem)

        promptData = loadPromptSidecar(img)
        if not promptData:
            logger.info("%s skip (no prompt sidecar): %s", prefix, rel)
            continue

        assembled = promptData.get("assembled", {})
        if not isinstance(assembled, dict):
            logger.info("%s skip (invalid sidecar assembled): %s", prefix, rel)
            continue

        positive = assembled.get("positive", "")
        negative = assembled.get("negative", "")
        if not isinstance(positive, str) or not positive.strip():
            logger.info("%s skip (missing positive prompt): %s", prefix, rel)
            continue
        if not isinstance(negative, str):
            negative = ""

        logger.info("%s [%d/%d] generating: %s", prefix, idx, len(images), rel)

        variants = max(1, int(args.variants))
        for v in range(1, variants + 1):
            # load fresh workflow each time (avoid bleed)
            workflow = loadWorkflow(wfPath)

            # patch workflow
            setClipText(workflow, "3", positive)
            setClipText(workflow, "4", negative)
            setEmptyLatent(workflow, "5", width, height, batchSize)

            seed = random.randint(1, 2**31 - 1)
            setKSampler(
                workflow,
                "6",
                seed=seed,
                steps=steps,
                cfg=cfgScale,
                sampler=sampler,
                scheduler=scheduler,
            )

            setLoraStrength(workflow, "2", loraModel, loraClip)

            savePrefix = prefixTemplate.format(fixed=fixedPrefix, stem=stem, v=v)
            setSavePrefix(workflow, savePrefix)

            logger.info("%s ...variant v%02d seed=%d prefix=%s", prefix, v, seed, savePrefix)

            if args.dry_run:
                continue

            try:
                assert client is not None
                pid = client.submit(workflow)
                hist = client.wait(pid, pollSeconds, maxWaitSeconds)
                outs = extractOutputImages(hist)

                if not outs:
                    logger.info("%s ...completed (no outputs): %s", prefix, rel)
                    continue

                # Save under runDir for traceability AND mirror to comfyOutput
                imgRunDir = runDir / "fullbody" / stem / f"v{v:02d}"
                ensureDir(imgRunDir, args.dry_run)

                for n, meta in enumerate(outs, start=1):
                    data = client.download(meta["filename"], meta.get("subfolder", ""), meta.get("type", "output"))
                    ext = Path(meta["filename"]).suffix or ".png"

                    # run folder copy
                    runFile = imgRunDir / f"out_{n:02d}{ext}"
                    runFile.write_bytes(data)

                    # mirror copy
                    mirrorName = f"{savePrefix}_{n:05d}_{ext}".replace("__", "_")
                    mirrorFile = comfyOutput / mirrorName
                    mirrorFile.write_bytes(data)

                logger.info("%s ...saved: %s", prefix, imgRunDir)

            except Exception as e:
                logger.error("Failed to generate %s (v%02d): %s", rel, v, e)

    logger.info("%s done.", prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
