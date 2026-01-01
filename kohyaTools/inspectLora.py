#!/usr/bin/env python3
"""
inspectLora.py

Inspect a .safetensors file (typically a LoRA) and print useful diagnostics:
- number of tensors, total parameters, approximate size
- dtype / shape summary
- rough classification (LoRA vs full checkpoint-like)
- counts of UNet vs Text Encoder tensors
- infer common LoRA rank from lora_up / lora_down shapes
- optional: compare two safetensors files (keys added/removed/common)

Conventions:
- prefix is "..." normally
- prefix is "...[]" when --dry-run is set (no file writes occur anyway, but kept for consistency)
- in a string write as below to include the prefix
-    print(f'{prefix} {message}')

Examples:
  python inspectLora.py myLora.safetensors
  python inspectLora.py myLora.safetensors --list-keys
  python inspectLora.py myLora.safetensors --top-shapes 20
  python inspectLora.py old.safetensors --compare new.safetensors
"""

from __future__ import annotations

import argparse
import sys

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from safetensors.torch import load_file


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect a LoRA / safetensors file.")
    parser.add_argument("file", type=Path, help="path to .safetensors file")
    parser.add_argument("--compare", type=Path, default=None, help="optional second .safetensors to compare against")

    parser.add_argument("--list-keys", action="store_true", help="print all tensor keys")
    parser.add_argument("--list-keys-like", type=str, default=None, help="print keys containing this substring (case-insensitive)")
    parser.add_argument("--top-shapes", type=int, default=0, help="print top N most common shapes")
    parser.add_argument("--top-dtypes", type=int, default=0, help="print top N most common dtypes")
    parser.add_argument("--max-keys", type=int, default=0, help="limit number of keys printed (0 = unlimited)")

    parser.add_argument("--dry-run", dest="dryRun", action="store_true", help="no-op; kept for consistency with toolchain")

    return parser.parse_args()


def loadSafeTensors(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    if path.suffix.lower() != ".safetensors":
        raise ValueError(f"not a .safetensors file: {path}")
    return load_file(str(path))


def approxTensorBytes(tensor) -> int:
    # torch tensors: element_size() exists
    try:
        return int(tensor.numel()) * int(tensor.element_size())
    except Exception:
        return 0


def humanBytes(num: int) -> str:
    # simple IEC units
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

    # Heuristics:
    # - LoRA typically contains "lora_" and "lora_up"/"lora_down" in keys.
    # - Full SD1.5-ish checkpoints often contain "model.diffusion_model" or "first_stage_model" etc.
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
    """
    Attempts to infer rank from lora_up/lora_down matrices.

    Typical patterns:
      - lora_up.weight shape: (out_features, rank) or (out_channels, rank, 1, 1)
      - lora_down.weight shape: (rank, in_features) or (rank, in_channels, 1, 1)

    We count observed ranks and return a sorted dict of rank -> occurrences.
    """
    rankCounts: Counter[int] = Counter()

    for k, t in data.items():
        kl = k.lower()
        if "lora_up" not in kl and "lora_down" not in kl:
            continue

        try:
            shape = tuple(int(x) for x in t.shape)
        except Exception:
            continue

        # Find a plausible rank:
        # - for 2D, one dimension is typically rank (often smaller than the other)
        # - for 4D conv (out, rank, 1, 1) or (rank, in, 1, 1)
        rank: Optional[int] = None

        if len(shape) == 2:
            a, b = shape
            rank = min(a, b)
        elif len(shape) == 4:
            # look for a non-1 dimension that is "small" compared to the other
            # common: (out, rank, 1, 1) or (rank, in, 1, 1)
            candidates = [d for d in shape if d != 1]
            if len(candidates) == 2:
                rank = min(candidates[0], candidates[1])

        if rank is not None:
            rankCounts[rank] += 1

    # return as normal dict sorted by count desc
    return dict(sorted(rankCounts.items(), key=lambda kv: (-kv[1], kv[0])))


def printKeyList(prefix: str, keys: List[str], maxKeys: int = 0) -> None:
    limit = maxKeys if maxKeys and maxKeys > 0 else len(keys)
    for i, k in enumerate(keys[:limit], start=1):
        print(f"{prefix}key {i:>5}: {k}")
    if limit < len(keys):
        print(f"{prefix}keys truncated: {limit}/{len(keys)} shown")


def compareKeys(prefix: str, leftName: str, leftKeys: List[str], rightName: str, rightKeys: List[str]) -> None:
    leftSet = set(leftKeys)
    rightSet = set(rightKeys)

    added = sorted(rightSet - leftSet)
    removed = sorted(leftSet - rightSet)
    common = sorted(leftSet & rightSet)

    print(f"{prefix} compare: {leftName} -> {rightName}")
    print(f"{prefix} keys: left={len(leftKeys)} right={len(rightKeys)} common={len(common)} added={len(added)} removed={len(removed)}")

    if added:
        print(f"{prefix} added (first 25):")
        for k in added[:25]:
            print(f"{prefix}  + {k}")
    if removed:
        print(f"{prefix} removed (first 25):")
        for k in removed[:25]:
            print(f"{prefix}  - {k}")


def main() -> None:
    args = parseArgs()
    prefix = "...[]" if args.dryRun else "..."

    try:
        leftData = loadSafeTensors(args.file)
    except Exception as e:
        sys.exit(f"ERROR: {e}")

    leftKeys = sorted(leftData.keys())
    fileType = detectFileType(leftKeys)
    parts = classifyParts(leftKeys)

    tensorCount, totalParams, totalBytes, dtypeCounts, shapeCounts = summarizeTensors(leftData)
    rankCounts = inferLoraRanks(leftData)

    print(f"{prefix} file: {args.file}")
    print(f"{prefix} type: {fileType}")
    print(f"{prefix} tensors: {tensorCount}")
    print(f"{prefix} params: {totalParams:,}")
    print(f"{prefix} approx tensor bytes: {humanBytes(totalBytes)}")
    print(f"{prefix} parts: unet={parts.get('unet', 0)} text_encoder={parts.get('text_encoder', 0)} other={parts.get('other', 0)} non-lora={parts.get('non-lora', 0)}")

    if rankCounts:
        # show top 5 ranks
        top = list(rankCounts.items())[:5]
        formatted = ", ".join([f"rank {r}: {c} tensors" for r, c in top])
        print(f"{prefix} rank inference: {formatted}")
    else:
        print(f"{prefix} rank inference: none (no lora_up/lora_down tensors detected)")

    if args.top_dtypes and args.top_dtypes > 0:
        print(f"{prefix} top dtypes:")
        for dtype, count in dtypeCounts.most_common(args.top_dtypes):
            print(f"{prefix}  {dtype}: {count}")

    if args.top_shapes and args.top_shapes > 0:
        print(f"{prefix} top shapes:")
        for shape, count in shapeCounts.most_common(args.top_shapes):
            print(f"{prefix}  {shape}: {count}")

    if args.list_keys_like:
        needle = args.list_keys_like.lower()
        filtered = [k for k in leftKeys if needle in k.lower()]
        print(f"{prefix} keys matching: '{args.list_keys_like}' ({len(filtered)})")
        printKeyList(prefix, filtered, maxKeys=args.max_keys)
    elif args.list_keys:
        print(f"{prefix} keys ({len(leftKeys)}):")
        printKeyList(prefix, leftKeys, maxKeys=args.max_keys)

    if args.compare:
        try:
            rightData = loadSafeTensors(args.compare)
        except Exception as e:
            sys.exit(f"ERROR: {e}")
        rightKeys = sorted(rightData.keys())
        compareKeys(prefix, args.file.name, leftKeys, args.compare.name, rightKeys)


if __name__ == "__main__":
    main()
