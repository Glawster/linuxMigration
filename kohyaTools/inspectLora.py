#!/usr/bin/env python3
"""
inspectLora.py

Inspect a .safetensors file (typically a LoRA) and print useful diagnostics.

Conventions:
- --dry-run kept for toolchain consistency (no side effects anyway)
- prefix = "...[]" if dryRun else "..."
- logging via organiseMyProjects.logUtils.getLogger
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from safetensors.torch import load_file

from organiseMyProjects.logUtils import getLogger  # type: ignore


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect a LoRA / safetensors file.")
    parser.add_argument("file", type=Path, help="path to .safetensors file")
    parser.add_argument("--compare", type=Path, default=None, help="optional second .safetensors to compare against")

    parser.add_argument("--list-keys", action="store_true", help="print all tensor keys")
    parser.add_argument("--list-keys-like", type=str, default=None, help="print keys containing this substring (case-insensitive)")
    parser.add_argument("--top-shapes", type=int, default=0, help="print top N most common shapes")
    parser.add_argument("--top-dtypes", type=int, default=0, help="print top N most common dtypes")
    parser.add_argument("--max-keys", type=int, default=0, help="limit number of keys printed (0 = unlimited)")

    parser.add_argument(
        "--confirm",
        action="store_true",
        help="execute changes (default is dry-run mode)",
    )

    return parser.parse_args()


def loadSafeTensors(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if path.suffix.lower() != ".safetensors":
        raise ValueError(f"not a .safetensors file: {path}")
    return load_file(str(path))


def approxTensorBytes(tensor) -> int:
    try:
        return int(tensor.numel()) * int(tensor.element_size())
    except Exception:
        return 0


def humanBytes(num: int) -> str:
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    value = float(num)
    for u in units:
        if value < 1024.0 or u == units[-1]:
            if u == "B":
                return f"{int(value)} {u}"
            return f"{value:.2f} {u}"
        value /= 1024.0
    return f"{value:.2f} TiB"


def detectFileType(keys: Iterable[str]) -> str:
    keysLower = [k.lower() for k in keys]
    hasLora = any("lora_" in k for k in keysLower) or any("lora_up" in k for k in keysLower) or any("lora_down" in k for k in keysLower)
    hasCheckpointLike = any(k.startswith("model.") for k in keysLower) or any("model.diffusion_model" in k for k in keysLower) or any("first_stage_model" in k for k in keysLower)

    if hasLora and not hasCheckpointLike:
        return "lora"
    if hasCheckpointLike and not hasLora:
        return "checkpoint-like"
    if hasLora and hasCheckpointLike:
        return "mixed"
    return "unknown"


def classifyParts(keys: Iterable[str]) -> Counter:
    counts = Counter()
    for k in keys:
        kl = k.lower()
        if "lora" not in kl:
            counts["non-lora"] += 1
            continue
        if "unet" in kl:
            counts["unet"] += 1
        elif "text" in kl or "text_encoder" in kl:
            counts["text_encoder"] += 1
        else:
            counts["other"] += 1
    return counts


def summarizeTensors(data: Dict[str, Any]) -> Tuple[int, int, int, Counter, Counter]:
    # returns: tensorCount, totalParams, totalBytes, dtypeCounts, shapeCounts
    tensorCount = len(data)
    totalParams = 0
    totalBytes = 0
    dtypeCounts = Counter()
    shapeCounts = Counter()

    for t in data.values():
        try:
            totalParams += int(t.numel())
        except Exception:
            pass
        totalBytes += approxTensorBytes(t)
        try:
            dtypeCounts[str(t.dtype)] += 1
        except Exception:
            dtypeCounts["unknown"] += 1
        try:
            shapeCounts[str(tuple(t.shape))] += 1
        except Exception:
            shapeCounts["unknown"] += 1

    return tensorCount, totalParams, totalBytes, dtypeCounts, shapeCounts


def inferLoraRanks(data: Dict[str, Any]) -> Dict[int, int]:
    rankCounts: Counter[int] = Counter()
    for k, t in data.items():
        kl = k.lower()
        if "lora_up" not in kl and "lora_down" not in kl:
            continue
        try:
            shape = tuple(int(x) for x in t.shape)
        except Exception:
            continue

        rank: Optional[int] = None
        if len(shape) == 2:
            a, b = shape
            rank = min(a, b)
        elif len(shape) == 4:
            candidates = [d for d in shape if d != 1]
            if len(candidates) == 2:
                rank = min(candidates[0], candidates[1])

        if rank is not None:
            rankCounts[rank] += 1

    return dict(sorted(rankCounts.items(), key=lambda kv: (-kv[1], kv[0])))


def logKeyList(logger, prefix: str, keys: List[str], maxKeys: int = 0) -> None:
    limit = maxKeys if maxKeys and maxKeys > 0 else len(keys)
    for i, k in enumerate(keys[:limit], start=1):
        logger.info("%s key %5d: %s", prefix, i, k)
    if limit < len(keys):
        logger.info("%s keys truncated: %d/%d shown", prefix, limit, len(keys))


def compareKeys(logger, prefix: str, leftName: str, leftKeys: List[str], rightName: str, rightKeys: List[str]) -> None:
    leftSet = set(leftKeys)
    rightSet = set(rightKeys)

    added = sorted(rightSet - leftSet)
    removed = sorted(leftSet - rightSet)
    common = sorted(leftSet & rightSet)

    logger.info("%s compare: %s -> %s", prefix, leftName, rightName)
    logger.info("%s keys: left=%d right=%d common=%d added=%d removed=%d", prefix, len(leftKeys), len(rightKeys), len(common), len(added), len(removed))

    if added:
        logger.info("%s added (first 25):", prefix)
        for k in added[:25]:
            logger.info("%s  + %s", prefix, k)
    if removed:
        logger.info("%s removed (first 25):", prefix)
        for k in removed[:25]:
            logger.info("%s  - %s", prefix, k)


def main() -> None:
    args = parseArgs()
    dryRun = True
    if args.confirm:
        dryRun = False
    prefix = "...[]" if dryRun else "..."
    logger = getLogger("inspectLora", includeConsole=True)

    try:
        leftData = loadSafeTensors(args.file)
    except Exception as e:
        sys.exit(f"ERROR: {e}")

    leftKeys = sorted(leftData.keys())
    fileType = detectFileType(leftKeys)
    parts = classifyParts(leftKeys)

    tensorCount, totalParams, totalBytes, dtypeCounts, shapeCounts = summarizeTensors(leftData)
    rankCounts = inferLoraRanks(leftData)

    logger.info("%s file: %s", prefix, args.file)
    logger.info("%s type: %s", prefix, fileType)
    logger.info("%s tensors: %d", prefix, tensorCount)
    logger.info("%s params: %s", prefix, f"{totalParams:,}")
    logger.info("%s approx tensor bytes: %s", prefix, humanBytes(totalBytes))
    logger.info("%s parts: unet=%d text_encoder=%d other=%d non-lora=%d", prefix, parts.get("unet", 0), parts.get("text_encoder", 0), parts.get("other", 0), parts.get("non-lora", 0))

    if rankCounts:
        top = list(rankCounts.items())[:5]
        formatted = ", ".join([f"rank {r}: {c} tensors" for r, c in top])
        logger.info("%s rank inference: %s", prefix, formatted)
    else:
        logger.info("%s rank inference: none (no lora_up/lora_down tensors detected)", prefix)

    if args.top_dtypes and args.top_dtypes > 0:
        logger.info("%s top dtypes:", prefix)
        for dtype, count in dtypeCounts.most_common(args.top_dtypes):
            logger.info("%s  %s: %d", prefix, dtype, count)

    if args.top_shapes and args.top_shapes > 0:
        logger.info("%s top shapes:", prefix)
        for shape, count in shapeCounts.most_common(args.top_shapes):
            logger.info("%s  %s: %d", prefix, shape, count)

    if args.list_keys_like:
        needle = args.list_keys_like.lower()
        filtered = [k for k in leftKeys if needle in k.lower()]
        logger.info("%s keys matching: '%s' (%d)", prefix, args.list_keys_like, len(filtered))
        logKeyList(logger, prefix, filtered, maxKeys=args.max_keys)
    elif args.list_keys:
        logger.info("%s keys (%d):", prefix, len(leftKeys))
        logKeyList(logger, prefix, leftKeys, maxKeys=args.max_keys)

    if args.compare:
        try:
            rightData = loadSafeTensors(args.compare)
        except Exception as e:
            sys.exit(f"ERROR: {e}")
        rightKeys = sorted(rightData.keys())
        compareKeys(logger, prefix, args.file.name, leftKeys, args.compare.name, rightKeys)


if __name__ == "__main__":
    main()
