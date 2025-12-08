#!/usr/bin/env python3
"""
fixMyJPGs.py

Scan a folder (and subfolders) for JPEG files and:

1. Normalise them into a DaVinci-Resolve-friendly format:
   - sRGB
   - baseline (non-progressive)
   - 4:2:0 subsampling
   - EXIF & weird metadata stripped

2. Optionally (if --ai-upscale is enabled):
   - Use Real-ESRGAN (realesrgan-ncnn-vulkan) to upscale up to a target
     long edge (default: 7680 for 8K UHD).
   - This inherently denoises and improves perceived detail.
   - We only upscale if the image is smaller than the target.

By default it overwrites files *in place* while preserving timestamps.
Use --suffix to write new files instead.
Use --dry-run to only print what would be done.
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageOps, UnidentifiedImageError


def is_jpeg(path: Path) -> bool:
    return path.suffix.lower() in {".jpg", ".jpeg"}


def find_realesrgan() -> Path | None:
    """Locate realesrgan-ncnn-vulkan on PATH, or return None."""
    exe = shutil.which("realesrgan-ncnn-vulkan")
    return Path(exe) if exe else None


def choose_scale_factor(width: int, height: int, target_long_edge: int, max_scale: int) -> int | None:
    """
    Decide what upscale factor to use (2, 4, or 8) to get as close as possible
    to target_long_edge without exceeding max_scale. Returns None if no upscale needed.
    """
    long_edge = max(width, height)
    if long_edge >= target_long_edge:
        return None

    factor_needed = target_long_edge / long_edge

    # Real-ESRGAN typically supports 2, 4, (and sometimes 8)
    candidates = [2, 4, 8]
    candidates = [f for f in candidates if f <= max_scale]

    for f in candidates:
        if factor_needed <= f:
            return f

    return max(candidates) if candidates else None


def ai_upscale_image(
    path: Path,
    realesrgan_bin: Path,
    target_long_edge: int,
    max_scale: int,
    dry_run: bool,
) -> Tuple[bool, str]:
    """
    Use realesrgan-ncnn-vulkan to upscale the image if it is below target_long_edge.
    Returns (changed, message).
    """
    try:
        with Image.open(path) as im:
            width, height = im.size
    except Exception as e:
        return False, f"ERROR reading size for AI upscale {path}: {e}"

    scale = choose_scale_factor(width, height, target_long_edge, max_scale)
    if scale is None:
        return False, f"OK (no AI upscale needed, already >= target): {path}"

    if dry_run:
        return True, f"[] would AI upscale x{scale} to ~8K: {path}"

    # Preserve timestamps
    try:
        stat = path.stat()
    except FileNotFoundError:
        stat = None

    tmp_out = path.with_suffix(f".x{scale}.tmp{path.suffix}")

    cmd = [
        str(realesrgan_bin),
        "-i", str(path),
        "-o", str(tmp_out),
        "-s", str(scale),
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        if tmp_out.exists():
            tmp_out.unlink()
        return False, f"ERROR AI upscaling {path}: {e}"

    # Replace original with upscaled
    try:
        tmp_out.replace(path)
    except Exception as e:
        if tmp_out.exists():
            tmp_out.unlink()
        return False, f"ERROR replacing original with AI upscaled {path}: {e}"

    # Restore timestamps
    if stat is not None:
        os.utime(path, (stat.st_atime, stat.st_mtime))

    return True, f"AI UPSCALED x{scale}: {path}"


def process_image(
    path: Path,
    overwrite: bool,
    suffix: str,
    dry_run: bool,
    ai_upscale: bool,
    realesrgan_bin: Path | None,
    target_long_edge: int,
    max_scale: int,
) -> Tuple[bool, str]:
    """
    Returns (changed, message)
    """
    try:
        img = Image.open(path)
        img.load()
    except UnidentifiedImageError:
        return False, f"SKIP (not a valid image?): {path}"
    except Exception as e:
        return False, f"ERROR opening {path}: {e}"

    # Decide output path
    if overwrite and not suffix:
        out_path = path
    else:
        out_path = path.with_name(path.stem + suffix + path.suffix)

    # We normalise *all* JPEGs; it's cheap and maximally robust.
    needs_fix = True

    if dry_run:
        msg = f"[] would normalise JPEG: {path} -> {out_path}"
        # Still report potential AI upscale separately below
    else:
        # Preserve timestamps
        try:
            stat = path.stat()
        except FileNotFoundError:
            stat = None

        try:
            # Normalise: convert to RGB, strip metadata, baseline, sRGB-ish
            img = img.convert("RGB")
            # Gentle auto-contrast for colour/levels cleanup
            img = ImageOps.autocontrast(img)

            img.save(
                out_path,
                format="JPEG",
                quality=95,
                subsampling="4:2:0",
                optimize=True,
                progressive=False,
            )

            # If overwriting, make sure original path is replaced
            if out_path != path and overwrite:
                path.unlink()
                out_path.rename(path)
                out_path = path

            # Restore timestamps
            if stat is not None:
                os.utime(out_path, (stat.st_atime, stat.st_mtime))

            msg = f"FIXED JPEG: {path}"
        except Exception as e:
            return False, f"ERROR saving {path}: {e}"

    changed = needs_fix

    # AI upscale step (optional)
    if ai_upscale:
        if not realesrgan_bin:
            ai_msg = f"SKIP AI (realesrgan-ncnn-vulkan not found): {path}"
        else:
            ai_changed, ai_msg = ai_upscale_image(
                out_path if not dry_run else path,
                realesrgan_bin,
                target_long_edge=target_long_edge,
                max_scale=max_scale,
                dry_run=dry_run,
            )
            if ai_changed:
                changed = True
        msg = f"{msg} | {ai_msg}"

    return changed, msg


def main():
    parser = argparse.ArgumentParser(description="Clean and optionally AI-upscale JPEGs for DaVinci Resolve.")
    parser.add_argument(
        "root",
        help="Root folder to scan (will recurse into subfolders).",
    )
    parser.add_argument(
        "--suffix",
        default="",
        help="Suffix to add before extension instead of overwriting (e.g. _fixed). "
             "If empty (default), files are overwritten in place.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not modify anything, just print what would be done.",
    )
    parser.add_argument(
        "--ai-upscale",
        action="store_true",
        help="Enable AI upscaling using realesrgan-ncnn-vulkan.",
    )
    parser.add_argument(
        "--target-long-edge",
        type=int,
        default=7680,
        help="Target long edge in pixels for AI upscaling (default: 7680 for ~8K).",
    )
    parser.add_argument(
        "--max-scale",
        type=int,
        default=8,
        help="Maximum AI scale factor to use (2, 4, or 8, default: 8).",
    )

    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()

    if not root.is_dir():
        print(f"ERROR: {root} is not a directory.")
        return

    overwrite = args.suffix == ""
    suffix = args.suffix

    realesrgan_bin = find_realesrgan() if args.ai_upscale else None
    if args.ai_upscale and not realesrgan_bin:
        print("WARNING: --ai-upscale enabled but realesrgan-ncnn-vulkan was not found on PATH.")
        print("         AI upscaling will be skipped for all files.\n")

    print(f"Scanning: {root}")
    print(f"Overwrite in place: {overwrite}")
    if suffix:
        print(f"Using suffix: {suffix}")
    print(f"AI upscaling: {args.ai_upscale}")
    if args.ai_upscale:
        print(f"  Target long edge: {args.target_long_edge}px")
        print(f"  Max scale factor: x{args.max_scale}")
        if realesrgan_bin:
            print(f"  Using realesrgan: {realesrgan_bin}")
    if args.dry_run:
        print("[] mode - no files will be changed.")
    print()

    total = 0
    changed = 0
    errors = 0
    skipped = 0

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if not is_jpeg(path):
            continue

        total += 1
        did_change, msg = process_image(
            path,
            overwrite=overwrite,
            suffix=suffix,
            dry_run=args.dry_run,
            ai_upscale=args.ai_upscale,
            realesrgan_bin=realesrgan_bin,
            target_long_edge=args.target_long_edge,
            max_scale=args.max_scale,
        )
        print(msg)
        if msg.startswith("ERROR"):
            errors += 1
        elif msg.startswith("SKIP"):
            skipped += 1
        elif did_change:
            changed += 1

    print()
    print(f"Done. JPEG files seen: {total}")
    print(f"Changed (fixed and/or AI upscaled): {changed}")
    print(f"Skipped: {skipped}, Errors: {errors}")


if __name__ == "__main__":
    main()
