#!/usr/bin/env python3
"""
fixMyJPGs.py

Scan a folder (and subfolders) for JPEG files and:

1. Normalise them into a DaVinci-Resolve-friendly format:
   - sRGB
   - baseline (non-progressive)
   - 4:2:0 subsampling
   - EXIF & weird metadata stripped
   - optional 16:9 aspect (crop or pad)

2. Optionally (if --ai-upscale is enabled):
   - Use Real-ESRGAN (realesrgan-ncnn-vulkan) to upscale up to a target
     long edge (default: 4096, i.e. ~4K for low-VRAM GPUs).
   - We only upscale if the image is smaller than the target.
   - We *never* overwrite with a black output: if the AI result looks
     essentially black, it is discarded and the original is kept.

By default it overwrites files *in place* while preserving timestamps.
Use --suffix to write new files instead.
Use --confirm to execute changes (dry-run mode is the default).
"""

import argparse
import os
import shutil
import subprocess
from pathlib import Path
from typing import Tuple, Optional

from PIL import Image, ImageOps, ImageStat, UnidentifiedImageError


def is_jpeg(path: Path) -> bool:
    return path.suffix.lower() in {".jpg", ".jpeg"}


def find_realesrgan() -> Optional[Path]:
    """Locate realesrgan-ncnn-vulkan on PATH, or return None."""
    exe = shutil.which("realesrgan-ncnn-vulkan")
    return Path(exe) if exe else None


def choose_scale_factor(width: int, height: int, target_long_edge: int, max_scale: int) -> Optional[int]:
    """
    Decide what upscale factor to use (2, 4, or 8) to get as close as possible
    to target_long_edge without exceeding max_scale. Returns None if no upscale needed.
    """
    long_edge = max(width, height)
    if long_edge >= target_long_edge:
        return None

    factor_needed = target_long_edge / long_edge

    candidates = [2, 4, 8]
    candidates = [f for f in candidates if f <= max_scale]

    for f in candidates:
        if factor_needed <= f:
            return f

    return max(candidates) if candidates else None


def crop_to_16_9(img: Image.Image) -> Image.Image:
    """Center-crop image to 16:9 without scaling."""
    w, h = img.size
    target_ratio = 16 / 9
    ratio = w / h

    if abs(ratio - target_ratio) < 1e-3:
        return img  # already ~16:9

    if ratio > target_ratio:
        # too wide -> crop width
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        box = (left, 0, left + new_w, h)
    else:
        # too tall -> crop height
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        box = (0, top, w, top + new_h)

    return img.crop(box)


def pad_to_16_9(img: Image.Image, fill=(0, 0, 0)) -> Image.Image:
    """Pad image to 16:9 with given background colour (default black)."""
    w, h = img.size
    target_ratio = 16 / 9
    ratio = w / h

    if abs(ratio - target_ratio) < 1e-3:
        return img  # already ~16:9

    if ratio > target_ratio:
        # too wide -> pad height
        new_h = int(w / target_ratio)
        new_w = w
    else:
        # too tall -> pad width
        new_w = int(h * target_ratio)
        new_h = h

    new_img = Image.new("RGB", (new_w, new_h), fill)
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    new_img.paste(img, (left, top))
    return new_img


def enforce_16_9(img: Image.Image, mode: Optional[str]) -> Image.Image:
    """
    mode: None, 'crop', or 'pad'
    """
    if mode is None:
        return img
    if mode == "crop":
        return crop_to_16_9(img)
    if mode == "pad":
        return pad_to_16_9(img)
    return img


def looks_black(path: Path, threshold_mean: float = 1.0, threshold_std: float = 2.0) -> bool:
    """
    Heuristic: open the image and see if it's essentially all black.
    - mean < threshold_mean
    - stddev < threshold_std (little variation)
    """
    try:
        im = Image.open(path).convert("RGB")
        stat = ImageStat.Stat(im)
        mean = stat.mean
        stddev = stat.stddev
    except Exception:
        return False  # if we can't read it, don't guess it's black

    if all(m <= threshold_mean for m in mean) and all(s <= threshold_std for s in stddev):
        return True
    return False


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
    Never overwrites the file with an all-black result.
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
        return True, f"[] would AI upscale x{scale} toward target: {path}"

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

    # Check for black output
    if not tmp_out.exists():
        return False, f"ERROR AI upscaling {path}: tmp output missing"

    if looks_black(tmp_out):
        tmp_out.unlink()
        return False, f"AI UPSCALE FAILED (black output, likely VRAM) for {path}"

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
    realesrgan_bin: Optional[Path],
    target_long_edge: int,
    max_scale: int,
    aspect_mode: Optional[str],
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

    if dry_run:
        msg = f"[] would normalise JPEG (incl. 16:9 {aspect_mode or 'none'}): {path} -> {out_path}"
        changed = True
    else:
        # Preserve timestamps
        try:
            stat = path.stat()
        except FileNotFoundError:
            stat = None

        try:
            # Normalise: convert to RGB
            img = img.convert("RGB")

            # Enforce 16:9 if requested (crop or pad)
            img = enforce_16_9(img, aspect_mode)

            # Gentle auto-contrast for colour/levels cleanup
            # this causes issues with some images, so disabled for now
            #img = ImageOps.autocontrast(img)

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

            msg = f"FIXED JPEG (16:9 {aspect_mode or 'none'}): {path}"
        except Exception as e:
            return False, f"ERROR saving {path}: {e}"

        changed = True

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
        "--confirm",
        action="store_true",
        help="Execute changes (default is dry-run mode).",
    )
    parser.add_argument(
        "--ai-upscale",
        action="store_true",
        help="Enable AI upscaling using realesrgan-ncnn-vulkan.",
    )
    parser.add_argument(
        "--target-long-edge",
        type=int,
        default=4096,
        help="Target long edge in pixels for AI upscaling "
             "(default: 4096, safer for 3GB GPUs).",
    )
    parser.add_argument(
        "--max-scale",
        type=int,
        default=2,
        help="Maximum AI scale factor to use (2, 4, or 8, default: 2 for low-VRAM GPUs).",
    )

    aspect_group = parser.add_mutually_exclusive_group()
    aspect_group.add_argument(
        "--no-16-9",
        action="store_true",
        help="Do not enforce 16:9 aspect ratio.",
    )
    aspect_group.add_argument(
        "--pad-16-9",
        action="store_true",
        help="Pad images to 16:9 instead of cropping (default is crop).",
    )

    args = parser.parse_args()
    args.dryRun = not args.confirm
    root = Path(args.root).expanduser().resolve()

    if not root.is_dir():
        print(f"ERROR: {root} is not a directory.")
        return

    overwrite = args.suffix == ""
    suffix = args.suffix

    # Aspect ratio mode: default 'crop' for DaVinci 16:9 timelines
    if args.no_16_9:
        aspect_mode = None
    elif args.pad_16_9:
        aspect_mode = "pad"
    else:
        aspect_mode = "crop"

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
    print(f"16:9 mode: {aspect_mode or 'none'}")
    if args.dryRun:
        print("[] no files will be changed.\n")
    else:
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
            dry_run=args.dryRun,
            ai_upscale=args.ai_upscale,
            realesrgan_bin=realesrgan_bin,
            target_long_edge=args.target_long_edge,
            max_scale=args.max_scale,
            aspect_mode=aspect_mode,
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
    print(f"Changed (fixed / 16:9 / AI upscaled): {changed}")
    print(f"Skipped: {skipped}, Errors: {errors}")


if __name__ == "__main__":
    main()
