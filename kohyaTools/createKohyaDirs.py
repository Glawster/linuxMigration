#!/usr/bin/env python3
"""
trainKohya.py

CPU-only LoRA training launcher for kohya_ss using DreamBooth-style folders.

Final layout:

  trainingRoot/
    styleName/
      10_styleName/      <-- trainDir (instance images)
      output/

Notes:
- trainDir is ALWAYS styleDir / f"10_{styleName}"
- kohya expects --train_data_dir to be the PARENT (styleDir)

Config:
- automatically reads/writes ~/.config/kohya/kohyaConfig.json
- CLI overrides config for this run
- if CLI changes values, config is updated (unless --dry-run)

Logging:
- prefix is "..." normally
- prefix is "...[] " when --dry-run is set
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List

from kohyaConfig import loadConfig, saveConfig, getCfgValue, updateCfgFromArgs


def resolveTrainScriptPath(kohyaDir: Path) -> Path:
    candidates = [
        kohyaDir / "train_network.py",
        kohyaDir / "sd-scripts" / "train_network.py",
        kohyaDir / "scripts" / "train_network.py",
    ]

    for path in candidates:
        if path.exists():
            return path

    raise FileNotFoundError(f"train_network.py not found under: {kohyaDir}")


def parseArgs() -> argparse.Namespace:
    cfg = loadConfig()

    defaultTrainingRoot = Path(
        getCfgValue(
            cfg,
            "trainingRoot",
            getCfgValue(cfg, "baseDataDir", "/mnt/myVideo/Adult/tumblrForMovie"),
        )
    )

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
        "--trainingRoot",
        type=Path,
        default=defaultTrainingRoot,
        help=f"root folder containing style training folders (default: {defaultTrainingRoot})",
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
        help=f"minimum required images in trainDir (default: {defaultMinImages})",
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
        dest="dry_run",
        action="store_true",
        help="show actions without executing",
    )

    return parser.parse_args()


def buildTrainingCommand(
    args: argparse.Namespace,
    styleDir: Path,
    trainScriptPath: Path,
) -> List[str]:
    outputDir = styleDir / "output"
    outputName = f"{args.styleName}_r{args.rank}_{args.resolution.replace(',', 'x')}"

    shellCommand = (
        f"cd {args.kohyaDir} && "
        f"source ~/miniconda3/etc/profile.d/conda.sh && "
        f"conda activate {args.condaEnvName} && "
        f"accelerate launch --num_cpu_threads_per_process={args.cpuThreads} "
        f"'{trainScriptPath}' "
        f"--pretrained_model_name_or_path='{args.baseModelPath}' "
        f"--train_data_dir='{styleDir}' "
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
    cfg = loadConfig()

    updates = {
        "trainingRoot": str(args.trainingRoot),
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
    if changed and not args.dry_run:
        saveConfig(cfg)

    return changed


def runTraining() -> None:
    args = parseArgs()
    prefix = "...[] " if args.dry_run else "..."

    trainingRoot = args.trainingRoot.expanduser().resolve()
    styleDir = trainingRoot / args.styleName
    trainDir = styleDir / f"10_{args.styleName}"

    baseModelPath = args.baseModelPath.expanduser().resolve()
    kohyaDir = args.kohyaDir.expanduser().resolve()

    print(f"{prefix}starting cpu-only lora training")
    print(f"{prefix}style: {args.styleName}")
    print(f"{prefix}training root: {trainingRoot}")
    print(f"{prefix}train dir: {trainDir}")
    print(f"{prefix}output dir: {styleDir / 'output'}")

    if not trainDir.exists():
        sys.exit(f"ERROR: train dir not found: {trainDir}")

    imageFiles = list(trainDir.glob("*.jpg")) + list(trainDir.glob("*.png"))
    if len(imageFiles) < args.minImages:
        sys.exit(f"ERROR: insufficient training images in {trainDir} ({len(imageFiles)} found)")

    if not baseModelPath.exists():
        sys.exit(f"ERROR: base model not found: {baseModelPath}")

    if not kohyaDir.exists():
        sys.exit(f"ERROR: kohya repo dir not found: {kohyaDir}")

    trainScriptPath = resolveTrainScriptPath(kohyaDir)
    print(f"{prefix}train script: {trainScriptPath}")

    configChanged = updateConfigFromArgs(args)
    if configChanged and not args.dry_run:
        print(f"{prefix}updated config: {Path.home() / '.config/kohya/kohyaConfig.json'}")

    command = buildTrainingCommand(
        args=args,
        styleDir=styleDir,
        trainScriptPath=trainScriptPath,
    )

    print(f"{prefix}training command: {command[2]}")

    if args.dry_run:
        print(f"{prefix}training skipped (--dry-run)")
        return

    print(f"{prefix}launching training")
    subprocess.run(command, check=True)
    print(f"{prefix}training complete")


if __name__ == "__main__":
    runTraining()
