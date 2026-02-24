#!/usr/bin/env python3
"""
UpscaleVideo.py

Upscale and enhance low-res 4:3-ish videos (e.g. 480p) using Real-ESRGAN x2
and output to 720p / 1080p / 4K with flexible aspect handling.

Pipeline:
1. Create <name>_upscale or <name>_upscale_N next to the source file.
   - 1st run: myVideo_upscale
   - 2nd run: myVideo_upscale -> myVideo_upscale_1, create myVideo_upscale_2 (use this)
   - 3rd run: existing _1, _2; create myVideo_upscale_3 (use this)
   - etc.
2. Extract frames (PNG) and audio via ffmpeg.
3. Run realesrgan-ncnn-vulkan (x2, model realesrgan-x2plus) on frames.
4. Assemble new video with ffmpeg:
   - target: 720p / 1080p / 4k (default 720p)
   - aspect: keep (4:3), pad (16:9 with pillarbox), crop (16:9)
5. Attach audio (if any).

The *_upscale* folders are always kept. Cleanup can be handled separately.
"""

import argparse
import shutil
import subprocess
from pathlib import Path
from typing import Tuple, List


def runCommand(cmd, dryRun: bool = False, desc: str = "") -> int:
    """Run a shell command with basic logging."""
    if desc:
        print(desc)
    print("  ", " ".join(str(x) for x in cmd))
    if dryRun:
        print("[] no command executed.\n")
        return 0
    print()
    result = subprocess.run(cmd)
    return result.returncode


def ensureTool(name: str) -> bool:
    return shutil.which(name) is not None


def getFps(inputPath: Path) -> float:
    """Use ffprobe to get video FPS, fall back to 25.0 on failure."""
    try:
        cmd = [
            "ffprobe",
            "-v", "0",
            "-of", "csv=p=0",
            "-select_streams", "v:0",
            "-show_entries", "stream=r_frame_rate",
            str(inputPath),
        ]
        out = subprocess.check_output(cmd, text=True).strip()
        if "/" in out:
            num, den = out.split("/")
            fps = float(num) / float(den)
        else:
            fps = float(out)
        if fps <= 0:
            raise ValueError
        return fps
    except Exception:
        print("WARNING: could not detect FPS, defaulting to 25.0")
        return 25.0


def buildFilter(target: str, aspect: str) -> str:
    """
    Build ffmpeg -vf filter string based on target resolution and aspect mode.

    target: '720p', '1080p', '4k'
    aspect:
      - 'keep': keep 4:3, set to 960x720 / 1440x1080 / 2880x2160
      - 'pad': pad to 16:9 (1280x720 / 1920x1080 / 3840x2160)
      - 'crop': crop to 16:9
    """
    if target == "720p":
        h = 720
        w16_9 = 1280
    elif target == "1080p":
        h = 1080
        w16_9 = 1920
    elif target == "4k":
        h = 2160
        w16_9 = 3840
    else:
        raise ValueError("Unknown target")

    w4_3 = int(round(h * 4 / 3))  # 4:3 width

    if aspect == "keep":
        # final = 4:3
        return f"scale={w4_3}:{h}"

    if aspect == "pad":
        # scale to 4:3 then pad to 16:9 with black bars
        xOffset = (w16_9 - w4_3) // 2
        return f"scale={w4_3}:{h},pad={w16_9}:{h}:{xOffset}:0:black"

    if aspect == "crop":
        # scale to full 16:9 width then crop height
        return f"scale={w16_9}:-2,crop={w16_9}:{h}"

    # fallback: no explicit aspect handling
    return "scale=-2:-2"


def pickUpscaleFolder(baseName: str, parentDir: Path, dryRun: bool) -> Path:
    """
    Implement the naming logic:

    1st run:
      - if myVideo_upscale does not exist, create it and use it.
    2nd run:
      - myVideo_upscale exists:
        - rename myVideo_upscale -> myVideo_upscale_1
        - create myVideo_upscale_2 and use it.
    3rd+ run:
      - myVideo_upscale no longer exists
      - myVideo_upscale_1, _2, ..., _N may exist
      - create myVideo_upscale_(N+1) and use it.
    """
    baseUpscale = parentDir / f"{baseName}_upscale"

    # Case 1: no base nor numbered folders exist -> first run, use baseUpscale
    if not baseUpscale.exists():
        # check if any numbered folders exist
        existingSuffixes = _findExistingUpscaleSuffixes(baseName, parentDir)
        if not existingSuffixes:
            if dryRun:
                print(f"[] would create upscale folder: {baseUpscale}")
            else:
                baseUpscale.mkdir(parents=True, exist_ok=False)
            return baseUpscale

    # If baseUpscale exists here, it's the "first" folder and we are on the second run
    if baseUpscale.exists():
        targetOld = parentDir / f"{baseName}_upscale_1"
        if dryRun:
            print(f"[] would rename {baseUpscale} -> {targetOld}")
        else:
            if targetOld.exists():
                # If somehow _1 already exists, find next unused for the old base
                k = 1
                while True:
                    cand = parentDir / f"{baseName}_upscale_{k}"
                    if not cand.exists():
                        targetOld = cand
                        break
                    k += 1
            baseUpscale.rename(targetOld)

    # At this point, baseUpscale should not be considered in use; we only use numbered suffixes
    existingSuffixes = _findExistingUpscaleSuffixes(baseName, parentDir)
    if not existingSuffixes:
        # No numbered folders? Then we can safely use baseUpscale again (rare edge case)
        if dryRun:
            print(f"[] would create upscale folder: {baseUpscale}")
        else:
            baseUpscale.mkdir(parents=True, exist_ok=False)
        return baseUpscale

    nextSuffix = max(existingSuffixes) + 1
    newUpscale = parentDir / f"{baseName}_upscale_{nextSuffix}"
    if dryRun:
        print(f"[] would create upscale folder: {newUpscale}")
    else:
        newUpscale.mkdir(parents=True, exist_ok=False)
    return newUpscale


def _findExistingUpscaleSuffixes(baseName: str, parentDir: Path) -> List[int]:
    """
    Find existing suffixes for folders like:
      baseName_upscale_1, baseName_upscale_2, ...
    Return list of ints.
    """
    suffixes: List[int] = []
    prefix = f"{baseName}_upscale_"
    for entry in parentDir.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name
        if name.startswith(prefix):
            tail = name[len(prefix):]
            if tail.isdigit():
                suffixes.append(int(tail))
    return suffixes


def main():
    parser = argparse.ArgumentParser(
        description="Upscale video with Real-ESRGAN x2 to 720p/1080p/4K, preserving 4:3 or converting to 16:9."
    )
    parser.add_argument("input", help="Input video file.")
    parser.add_argument(
        "--target",
        choices=["720p", "1080p", "4k"],
        default="720p",
        help="Target resolution (default: 720p).",
    )
    parser.add_argument(
        "--aspect",
        choices=["keep", "pad", "crop"],
        default="keep",
        help="Aspect handling: 'keep' 4:3, 'pad' to 16:9, or 'crop' to 16:9 (default: keep).",
    )
    parser.add_argument(
        "--model",
        default="realesrgan-x2plus",
        help="Real-ESRGAN model name (default: realesrgan-x2plus).",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Execute the upscaling process (default is dry-run mode).",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=18,
        help="CRF for x264 encoding (lower = higher quality, default 18).",
    )
    args = parser.parse_args()
    args.dryRun = not args.confirm

    inputPath = Path(args.input).expanduser().resolve()
    if not inputPath.is_file():
        print(f"ERROR: input file not found: {inputPath}")
        return

    # Tool checks
    missingTools = []
    for tool in ["ffmpeg", "ffprobe", "realesrgan-ncnn-vulkan"]:
        if not ensureTool(tool):
            missingTools.append(tool)
    if missingTools:
        print(f"ERROR: missing required tools: {', '.join(missingTools)}")
        print("Make sure they are installed and on PATH.")
        return

    fps = getFps(inputPath)

    parentDir = inputPath.parent
    baseName = inputPath.stem

    upscaleDir = pickUpscaleFolder(baseName, parentDir, args.dryRun)

    framesDir = upscaleDir / "frames"
    upscaledDir = upscaleDir / "upscaled"
    audioPath = upscaleDir / "audio.m4a"

    print(f"Input          : {inputPath}")
    print(f"Upscale folder : {upscaleDir}")
    print(f"Target         : {args.target}")
    print(f"Aspect         : {args.aspect}")
    print(f"FPS            : {fps:.3f}")
    print()

    # Create folder structure (frames, upscaled) if not dryRun
    if args.dryRun:
        print(f"[] would create frames dir   : {framesDir}")
        print(f"[] would create upscaled dir : {upscaledDir}\n")
    else:
        framesDir.mkdir(parents=True, exist_ok=True)
        upscaledDir.mkdir(parents=True, exist_ok=True)

    # 1) Extract frames
    extractFramesCmd = [
        "ffmpeg",
        "-y",
        "-i", str(inputPath),
        "-vsync", "0",
        str(framesDir / "frame_%08d.png"),
    ]
    rc = runCommand(extractFramesCmd, dryRun=args.dryRun, desc="Extracting frames...")
    if rc != 0 and not args.dryRun:
        print("ERROR: failed to extract frames.")
        return

    # 2) Extract audio (if present)
    extractAudioCmd = [
        "ffmpeg",
        "-y",
        "-i", str(inputPath),
        "-vn",
        "-c:a", "aac",
        "-b:a", "192k",
        str(audioPath),
    ]
    rcAudio = runCommand(extractAudioCmd, dryRun=args.dryRun, desc="Extracting audio (if any)...")
    if rcAudio != 0 and not args.dryRun:
        print("WARNING: failed to extract audio; output will be silent.")
        audioExists = False
    else:
        audioExists = True

    # 3) Real-ESRGAN x2 on frames
    realesrganCmd = [
        "realesrgan-ncnn-vulkan",
        "-i", str(framesDir),
        "-o", str(upscaledDir),
        "-s", "2",
        "-n", args.model,
    ]
    rc = runCommand(realesrganCmd, dryRun=args.dryRun, desc="Running Real-ESRGAN x2 on frames...")
    if rc != 0 and not args.dryRun:
        print("ERROR: Real-ESRGAN failed.")
        return

    # 4) Assemble final video with ffmpeg from upscaled frames
    vfFilter = buildFilter(args.target, args.aspect)
    print(f"Using ffmpeg video filter: {vfFilter}\n")

    suffixMap = {
        "720p": "720pAI",
        "1080p": "1080pAI",
        "4k": "4kAI",
    }
    outputPath = upscaleDir / f"{baseName}_{suffixMap[args.target]}.mp4"

    ffmpegCmd = [
        "ffmpeg",
        "-y",
        "-framerate", f"{fps}",
        "-i", str(upscaledDir / "frame_%08d.png"),
    ]
    if audioExists:
        ffmpegCmd += ["-i", str(audioPath)]
    ffmpegCmd += [
        "-vf", vfFilter,
        "-c:v", "libx264",
        "-crf", str(args.crf),
        "-preset", "slow",
        "-pix_fmt", "yuv420p",
    ]
    if audioExists:
        ffmpegCmd += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        ffmpegCmd += ["-an"]
    ffmpegCmd.append(str(outputPath))

    rc = runCommand(ffmpegCmd, dryRun=args.dryRun, desc="Encoding final upscaled video...")
    if rc != 0 and not args.dryRun:
        print("ERROR: failed to encode final video.")
        return

    if not args.dryRun:
        print(f"Done. Output written to : {outputPath}")
        print(f"Source remains at       : {inputPath}")
        print(f"All working files       : {upscaleDir}")


if __name__ == "__main__":
    main()
