#!/usr/bin/env python3
"""
trainKohya.py

CPU-only LoRA training launcher for kohya_ss using the standard layout:

  baseDataDir/
    styleName/
      train/
      output/
      originals/ (optional)

Config:
- automatically reads/writes ~/.config/kohya/kohyaConfig.json
- CLI overrides config for this run
- if CLI changes values, config is updated (unless --dry-run)

Logging:
- prefix is "..." normally
- prefix is "...[] " when --dry-run is set

Usage:
  python trainKohya.py kathy
  python trainKohya.py kathy --epochs 8
  python trainKohya.py kathy --dry-run
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List

from kohyaUtils import ensureDirs, resolveKohyaPaths, validateTrainingSet
from kohyaConfig import loadConfig, saveConfig, getCfgValue, updateCfgFromArgs


def parseArgs() -> argparse.Namespace:
    """
    Parse command-line arguments with defaults loaded from config.
    
    Returns:
        Parsed command-line arguments
    """
    cfg = loadConfig()

    defaultBaseDataDir = Path(getCfgValue(cfg, "baseDataDir", "/mnt/myVideo/Adult/tumblrForMovie"))
    defaultBaseModelPath = Path(getCfgValue(cfg, "baseModelPath", "/mnt/models/v1-5-pruned-emaonly.safetensors"))
    defaultKohyaDir = Path(getCfgValue(cfg, "kohyaDir", str(Path.home() / "Source/kohya_ss")))
    defaultCondaEnvName = getCfgValue(cfg, "condaEnvName", "kohya")

    defaultEpochs = int(getCfgValue(cfg, "epochs", 10))
    defaultCpuThreads = int(getCfgValue(cfg, "cpuThreads", 8))
    defaultMinImages = int(getCfgValue(cfg, "minImages", 12))

    defaultCaptionExtension = getCfgValue(cfg, "captionExtension", ".txt")

    defaultResolution = getCfgValue(cfg, "resolution", "512,512")
    defaultRank = int(getCfgValue(cfg, "rank", 8))
    defaultAlpha = int(getCfgValue(cfg, "alpha", 8))
    defaultLearningRate = float(getCfgValue(cfg, "learningRate", 1e-4))
    defaultTextEncoderLr = float(getCfgValue(cfg, "textEncoderLr", 5e-5))
    defaultUnetLr = float(getCfgValue(cfg, "unetLr", 1e-4))

    parser = argparse.ArgumentParser(description="CPU-only LoRA training launcher (kohya_ss, SD1.5).")

    parser.add_argument("styleName", help="style / person name (e.g. kathy)")

    parser.add_argument(
        "--baseDataDir",
        type=Path,
        default=defaultBaseDataDir,
        help=f"base dataset directory (default: {defaultBaseDataDir})",
    )

    parser.add_argument(
        "--baseModelPath",
        type=Path,
        default=defaultBaseModelPath,
        help=f"SD1.5 checkpoint path (default: {defaultBaseModelPath})",
    )

    parser.add_argument(
        "--kohyaDir",
        type=Path,
        default=defaultKohyaDir,
        help=f"kohya_ss repo directory (default: {defaultKohyaDir})",
    )

    parser.add_argument(
        "--condaEnvName",
        type=str,
        default=defaultCondaEnvName,
        help=f"conda env name (default: {defaultCondaEnvName})",
    )

    parser.add_argument("--epochs", type=int, default=defaultEpochs, help=f"max train epochs (default: {defaultEpochs})")
    parser.add_argument(
        "--cpuThreads",
        type=int,
        default=defaultCpuThreads,
        help=f"accelerate cpu threads (default: {defaultCpuThreads})",
    )
    parser.add_argument(
        "--minImages",
        type=int,
        default=defaultMinImages,
        help=f"minimum required images (default: {defaultMinImages})",
    )

    parser.add_argument(
        "--captionExtension",
        type=str,
        default=defaultCaptionExtension,
        help=f"caption extension (default: {defaultCaptionExtension})",
    )

    parser.add_argument(
        "--resolution",
        type=str,
        default=defaultResolution,
        help=f"training resolution (default: {defaultResolution})",
    )
    parser.add_argument("--rank", type=int, default=defaultRank, help=f"LoRA rank/network dim (default: {defaultRank})")
    parser.add_argument("--alpha", type=int, default=defaultAlpha, help=f"LoRA alpha (default: {defaultAlpha})")

    parser.add_argument(
        "--learningRate",
        type=float,
        default=defaultLearningRate,
        help=f"learning rate (default: {defaultLearningRate})",
    )
    parser.add_argument(
        "--textEncoderLr",
        type=float,
        default=defaultTextEncoderLr,
        help=f"text encoder lr (default: {defaultTextEncoderLr})",
    )
    parser.add_argument(
        "--unetLr",
        type=float,
        default=defaultUnetLr,
        help=f"u-net lr (default: {defaultUnetLr})",
    )

    parser.add_argument(
        "--dry-run",
        dest="dryRun",
        action="store_true",
        help="show actions without executing",
    )

    return parser.parse_args()


def buildTrainingCommand(args: argparse.Namespace, trainDir: Path, outputDir: Path) -> List[str]:
    """
    Build the complete training command for kohya_ss.
    
    Args:
        args: Parsed command-line arguments
        trainDir: Training data directory
        outputDir: Output directory for trained models
        
    Returns:
        Command list suitable for subprocess.run()
    """
    outputName = f"{args.styleName}_r{args.rank}_{args.resolution.replace(',', 'x')}"

    shellCommand = (
        f"cd {args.kohyaDir} && "
        f"source ~/miniconda3/etc/profile.d/conda.sh && "
        f"conda activate {args.condaEnvName} && "
        f"accelerate launch --num_cpu_threads_per_process={args.cpuThreads} "
        f"train_network.py "
        f"--pretrained_model_name_or_path='{args.baseModelPath}' "
        f"--train_data_dir='{trainDir}' "
        f"--output_dir='{outputDir}' "
        f"--output_name='{outputName}' "
        f"--caption_extension='{args.captionExtension}' "
        f"--resolution='{args.resolution}' "
        f"--enable_bucket "
        f"--min_bucket_reso=320 "
        f"--max_bucket_reso=768 "
        f"--bucket_reso_steps=64 "
        f"--network_module=networks.lora "
        f"--network_dim={args.rank} "
        f"--network_alpha={args.alpha} "
        f"--train_batch_size=1 "
        f"--gradient_accumulation_steps=1 "
        f"--max_train_epochs={args.epochs} "
        f"--learning_rate={args.learningRate} "
        f"--text_encoder_lr={args.textEncoderLr} "
        f"--unet_lr={args.unetLr} "
        f"--optimizer_type=AdamW "
        f"--lr_scheduler=cosine "
        f"--lr_warmup_steps=50 "
        f"--mixed_precision=no "
        f"--save_every_n_epochs=1 "
        f"--save_model_as=safetensors "
        f"--clip_skip=2"
    )

    return ["bash", "-lc", shellCommand]


def updateConfigFromArgs(args: argparse.Namespace) -> bool:
    """
    Update configuration file with command-line arguments.
    
    Args:
        args: Parsed command-line arguments
        
    Returns:
        True if configuration was changed, False otherwise
    """
    cfg = loadConfig()

    updates = {
        "baseDataDir": str(args.baseDataDir),
        "baseModelPath": str(args.baseModelPath),
        "kohyaDir": str(args.kohyaDir),
        "condaEnvName": args.condaEnvName,
        "epochs": args.epochs,
        "cpuThreads": args.cpuThreads,
        "minImages": args.minImages,
        "captionExtension": args.captionExtension,
        "resolution": args.resolution,
        "rank": args.rank,
        "alpha": args.alpha,
        "learningRate": args.learningRate,
        "textEncoderLr": args.textEncoderLr,
        "unetLr": args.unetLr,
    }

    changed = updateCfgFromArgs(cfg, updates)
    if changed and not args.dryRun:
        saveConfig(cfg)

    return changed


def runTraining() -> None:
    """
    Main entry point: parse arguments, validate setup, and launch training.
    
    Raises:
        SystemExit: On validation failures or missing dependencies
    """
    args = parseArgs()
    prefix = "...[]" if args.dryRun else "..."

    baseDataDir = args.baseDataDir.expanduser().resolve()
    baseModelPath = args.baseModelPath.expanduser().resolve()
    kohyaDir = args.kohyaDir.expanduser().resolve()

    kohyaPaths = resolveKohyaPaths(styleName=args.styleName, baseDataDir=baseDataDir)
    ensureDirs(kohyaPaths)

    print(f"{prefix} starting cpu-only lora training")
    print(f"{prefix} style: {args.styleName}")
    print(f"{prefix} base data dir: {baseDataDir}")
    print(f"{prefix} train dir: {kohyaPaths.trainDir}")
    print(f"{prefix} output dir: {kohyaPaths.outputDir}")

    if not baseModelPath.exists():
        print(f"ERROR: base model not found: {baseModelPath}")
        sys.exit(1)

    if not kohyaDir.exists():
        print(f"ERROR: kohya repo dir not found: {kohyaDir}")
        sys.exit(1)

    problems = validateTrainingSet(
        trainDir=kohyaPaths.trainDir,
        minImages=args.minImages,
        captionExtension=args.captionExtension,
        requireCaptions=True,
        recursive=False,
    )

    if problems:
        print("ERROR: training set validation failed:")
        for problem in problems:
            print(f"  - {problem}")
        sys.exit(1)

    configChanged = updateConfigFromArgs(args)
    if configChanged and not args.dryRun:
        print(f"{prefix} updated config: {Path.home() / '.config/kohya/kohyaConfig.json'}")

    command = buildTrainingCommand(args, trainDir=kohyaPaths.trainDir, outputDir=kohyaPaths.outputDir)

    print(f"{prefix} training command: {command[2]}")

    if args.dryRun:
        print(f"{prefix} training skipped (--dry-run)")
        return

    print(f"{prefix} launching training")
    subprocess.run(command, check=True)
    print(f"{prefix} training complete")


if __name__ == "__main__":
    runTraining()
