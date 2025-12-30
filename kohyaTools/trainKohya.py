#!/usr/bin/env python3
"""
trainKohya.py

CPU-only LoRA training launcher for kohya_ss using the standard layout:

  baseDataDir/
    styleName/
      train/
      output/
      originals/ (optional)

Usage:
  python trainKohya.py kathy
  python trainKohya.py kathy --baseDataDir /mnt/otherDisk/datasets
  python trainKohya.py kathy --epochs 8
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from pathlib import Path
from typing import List

from kohyaTools.kohyaUtils import ensureDirs, resolveKohyaPaths, validateTrainingSet


defaultBaseDataDir = Path("/mnt/myVideo/Adult/tumblrForMovie")
defaultBaseModelPath = Path("/mnt/models/v1-5-pruned-emaonly.safetensors")
defaultKohyaDir = Path.home() / "Source/kohya_ss"
defaultCondaEnvName = "kohya"


def parseArgs() -> argparse.Namespace:
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

    parser.add_argument("--epochs", type=int, default=10, help="max train epochs (default: 10)")
    parser.add_argument("--cpuThreads", type=int, default=8, help="accelerate cpu threads (default: 8)")
    parser.add_argument("--minImages", type=int, default=12, help="minimum required images (default: 12)")

    parser.add_argument("--captionExtension", type=str, default=".txt", help="caption extension (default: .txt)")

    # Training parameters you may want to tweak later
    parser.add_argument("--resolution", type=str, default="512,512", help="training resolution (default: 512,512)")
    parser.add_argument("--rank", type=int, default=8, help="LoRA rank/network dim (default: 8)")
    parser.add_argument("--alpha", type=int, default=8, help="LoRA alpha (default: 8)")
    parser.add_argument("--learningRate", type=float, default=1e-4, help="learning rate (default: 1e-4)")
    parser.add_argument("--textEncoderLr", type=float, default=5e-5, help="text encoder lr (default: 5e-5)")
    parser.add_argument("--unetLr", type=float, default=1e-4, help="u-net lr (default: 1e-4)")

    parser.add_argument("--dry-run", action="store_true", help="print command and exit without running")

    return parser.parse_args()


def buildTrainingCommand(args: argparse.Namespace, trainDir: Path, outputDir: Path) -> List[str]:
    outputName = f"{args.styleName}_r{args.rank}_{args.resolution.replace(',', 'x')}"

    # Single bash -lc command so conda activation works consistently
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


def runTraining() -> None:
    args = parseArgs()

    baseDataDir = args.baseDataDir.expanduser().resolve()
    baseModelPath = args.baseModelPath.expanduser().resolve()
    kohyaDir = args.kohyaDir.expanduser().resolve()

    kohyaPaths = resolveKohyaPaths(styleName=args.styleName, baseDataDir=baseDataDir)
    ensureDirs(kohyaPaths)

    prefix = "...[] " if args.dry_run else "..."
    print(f"{prefix}starting cpu-only lora training")
    print(f"{prefix}style: {args.styleName}")
    print(f"{prefix}base data dir: {baseDataDir}")
    print(f"{prefix}train dir: {kohyaPaths.trainDir}")
    print(f"{prefix}output dir: {kohyaPaths.outputDir}")
    print(f"{prefix}base model: {baseModelPath}")
    print(f"{prefix}kohya dir: {kohyaDir}")

    if not baseModelPath.exists():
        sys.exit(f"ERROR: base model not found: {baseModelPath}")

    if not kohyaDir.exists():
        sys.exit(f"ERROR: kohya repo dir not found: {kohyaDir}")

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

    command = buildTrainingCommand(args, trainDir=kohyaPaths.trainDir, outputDir=kohyaPaths.outputDir)

    print(f"...{prefix}training command:")
    print(command[2])
    if args.dry_run:
        print("...dryRun set, exiting without running")
        return

    print(f"...{prefix}launching training")
    subprocess.run(command, check=True)
    print(f"...{prefix}training complete")


if __name__ == "__main__":
    runTraining()
