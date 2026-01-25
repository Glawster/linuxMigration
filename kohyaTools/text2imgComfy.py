#!/usr/bin/env python3
"""
txt2imgComfy.py

Run a ComfyUI *text2img* workflow using pre-generated prompt sidecars.

Rules:
- One input image == one .prompt.json sidecar
- NO prompt generation here
- If sidecar missing -> log + skip
- Full-body only
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Dict, Any, List

import requests

from kohyaConfig import (  # type: ignore
    loadConfig,
    getCfgValue,
    updateConfigFromArgs,
    saveConfig,
    setLogger,
    DEFAULT_CONFIG_PATH,
)
from organiseMyProjects.logUtils import getLogger  # type: ignore

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def safeStem(stem: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in stem).strip("_")


def loadPromptSidecar(imgPath: Path) -> Dict[str, Any] | None:
    sidecar = imgPath.with_suffix(".prompt.json")
    if not sidecar.exists():
        return None
    with sidecar.open("r", encoding="utf-8") as f:
        return json.load(f)


def loadWorkflow(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------
# workflow patch helpers (node IDs fixed to your workflow)
# ------------------------------------------------------------------

def setClipText(prompt: Dict[str, Any], nodeId: str, text: str) -> None:
    node = prompt[nodeId]
    node["inputs"]["text"] = text


def setEmptyLatent(prompt: Dict[str, Any], nodeId: str, w: int, h: int, batch: int) -> None:
    node = prompt[nodeId]
    node["inputs"]["width"] = w
    node["inputs"]["height"] = h
    node["inputs"]["batch_size"] = batch


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
    node["inputs"]["seed"] = seed
    node["inputs"]["steps"] = steps
    node["inputs"]["cfg"] = cfg
    node["inputs"]["sampler_name"] = sampler
    node["inputs"]["scheduler"] = scheduler


def setLoraStrength(prompt: Dict[str, Any], nodeId: str, model: float, clip: float) -> None:
    node = prompt[nodeId]
    node["inputs"]["strength_model"] = model
    node["inputs"]["strength_clip"] = clip


def setSavePrefix(prompt: Dict[str, Any], prefix: str) -> None:
    for node in prompt.values():
        if node.get("class_type") == "SaveImage":
            node["inputs"]["filename_prefix"] = prefix


# ------------------------------------------------------------------
# ComfyUI client
# ------------------------------------------------------------------

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
        return r.json()["prompt_id"]

    def wait(self, promptId: str, poll: float, maxWait: int) -> Dict[str, Any]:
        start = time.time()
        while True:
            r = self.session.get(
                f"{self.baseUrl}/history/{promptId}",
                timeout=self.timeout,
            )
            r.raise_for_status()
            hist = r.json()
            if promptId in hist and hist[promptId].get("outputs"):
                return hist[promptId]
            if time.time() - start > maxWait:
                raise TimeoutError(promptId)
            time.sleep(poll)

    def download(self, filename: str, subfolder: str, kind: str) -> bytes:
        r = self.session.get(
            f"{self.baseUrl}/view",
            params={"filename": filename, "subfolder": subfolder, "type": kind},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.content


# ------------------------------------------------------------------
# args
# ------------------------------------------------------------------

def parseArgs(cfg: Dict[str, Any]) -> argparse.Namespace:
    p = argparse.ArgumentParser("Run text2img via ComfyUI using sidecar prompts")

    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--variants", type=int, default=1)

    p.add_argument("--local", help="local ComfyUI url")
    p.add_argument("--remote", help="remote ComfyUI url")

    p.add_argument("--comfyin", type=Path, default=Path(getCfgValue(cfg, "comfyInput")))
    p.add_argument("--comfyout", type=Path, default=Path(getCfgValue(cfg, "comfyOutput")))
    p.add_argument("--workflows", type=Path, default=Path(getCfgValue(cfg, "comfyWorkflowsDir")))
    p.add_argument("--runsdir", type=Path, default=Path(getCfgValue(cfg, "comfyRunsDir")))

    p.add_argument("--steps", type=int, default=int(getCfgValue(cfg, "comfyText2ImgSteps", 30)))
    p.add_argument("--cfg", type=float, default=float(getCfgValue(cfg, "comfyText2ImgCfg", 6.0)))
    p.add_argument("--sampler", default=getCfgValue(cfg, "comfyText2ImgSampler", "dpmpp_2m"))
    p.add_argument("--scheduler", default=getCfgValue(cfg, "comfyText2ImgScheduler", "karras"))
    p.add_argument("--width", type=int, default=int(getCfgValue(cfg, "comfyText2ImgWidth", 768)))
    p.add_argument("--height", type=int, default=int(getCfgValue(cfg, "comfyText2ImgHeight", 1024)))
    p.add_argument("--batch", type=int, default=int(getCfgValue(cfg, "comfyText2ImgBatchSize", 1)))
    p.add_argument("--loraModel", type=float, default=float(getCfgValue(cfg, "comfyText2ImgLoraStrengthModel", 1.0)))
    p.add_argument("--loraClip", type=float, default=float(getCfgValue(cfg, "comfyText2ImgLoraStrengthClip", 1.0)))

    p.add_argument("--timeout", type=int, default=int(getCfgValue(cfg, "comfyTimeoutSeconds", 120)))
    p.add_argument("--poll", type=float, default=float(getCfgValue(cfg, "comfyPollSeconds", 1.0)))
    p.add_argument("--maxwait", type=int, default=int(getCfgValue(cfg, "comfyMaxWaitSeconds", 1800)))

    return p.parse_args()


# ------------------------------------------------------------------
# main
# ------------------------------------------------------------------

def main() -> int:
    cfg = loadConfig()
    args = parseArgs(cfg)

    prefix = "...[]" if args.dry_run else "..."
    logger = getLogger("txt2imgComfy", includeConsole=True)
    setLogger(logger)

    if args.local and args.remote:
        logger.error("use --local or --remote, not both")
        return 2

    baseUrl = args.remote or args.local or getCfgValue(cfg, "comfyUrl")
    if not baseUrl:
        logger.error("no comfyui url provided")
        return 2

    wfName = getCfgValue(cfg, "comfyText2ImgWorkflow", "kathy-text-2-image-api.json")
    wfPath = args.workflows / wfName
    if not wfPath.exists():
        logger.error("workflow missing: %s", wfPath)
        return 2

    client = ComfyClient(baseUrl, args.timeout)

    images = [
        p for p in args.comfyin.rglob("*")
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]

    if args.limit:
        images = images[: args.limit]

    runDir = args.runsdir / f"run_{time.strftime('%Y%m%d_%H%M%S')}"
    runDir.mkdir(parents=True, exist_ok=True)

    logger.info("%s run dir: %s", prefix, runDir)
    logger.info("%s images: %d", prefix, len(images))

    for img in images:
        rel = img.relative_to(args.comfyin)
        stem = safeStem(img.stem)

        promptData = loadPromptSidecar(img)
        if not promptData:
            logger.info("%s skip (no prompt sidecar): %s", prefix, rel)
            continue

        pos = promptData["assembled"]["positive"]
        neg = promptData["assembled"]["negative"]

        for v in range(1, args.variants + 1):
            workflow = loadWorkflow(wfPath)

            seed = random.randint(1, 2**31 - 1)

            setClipText(workflow, "3", pos)
            setClipText(workflow, "4", neg)
            setEmptyLatent(workflow, "5", args.width, args.height, args.batch)
            setKSampler(
                workflow,
                "6",
                seed=seed,
                steps=args.steps,
                cfg=args.cfg,
                sampler=args.sampler,
                scheduler=args.scheduler,
            )
            setLoraStrength(workflow, "2", args.loraModel, args.loraClip)
            setSavePrefix(workflow, f"fixed_{stem}_t2i_v{v:02d}")

            logger.info("%s generating: %s (v%02d)", prefix, rel, v)

            if args.dry_run:
                continue

            try:
                pid = client.submit(workflow)
                hist = client.wait(pid, args.poll, args.maxwait)

                for node in hist["outputs"].values():
                    for imgMeta in node.get("images", []):
                        data = client.download(
                            imgMeta["filename"],
                            imgMeta.get("subfolder", ""),
                            imgMeta.get("type", "output"),
                        )
                        outFile = args.comfyout / imgMeta["filename"]
                        outFile.write_bytes(data)

            except Exception as e:
                logger.error("generation failed: %s", e)

    logger.info("%s done.", prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
