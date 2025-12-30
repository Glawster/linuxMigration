#!/usr/bin/env python3
"""
CPU-only LoRA training launcher for kohya_ss.

Usage:
  python trainKohya.py kathy
  python trainKohya.py kathy --baseDataDir /mnt/otherDisk/datasets
"""

import argparse
import subprocess
import sys
from pathlib import Path


defaultBaseDataDir = Path("/mnt/myVideo/Adult/tumblrForMovie")
baseModelPath = Path("/mnt/models/v1-5-pruned-emaonly.safetensors")
kohyaDir = Path.home() / "Source/kohya_ss"
condaEnvName = "kohya"


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CPU-only LoRA training launcher (kohya_ss, SD1.5)"
    )

    parser.add_argument(
        "styleName",
        help="style / person name (e.g. kathy)"
    )

    parser.add_argument(
        "--baseDataDir",
        type=Path,
        default=defaultBaseDataDir,
        help=f"base dataset directory (default: {defaultBaseDataDir})"
    )

    parser.add_argument(
        "--epochs",
        type=int,
        default=10,
        help="number of training epochs (default: 10)"
    )

    parser.add_argument(
        "--cpuThreads",
        type=int,
        default=8,
        help="number of CPU threads for accelerate (default: 8)"
    )

    return parser.parse_args()


def runTraining() -> None:
    args = parseArgs()

    trainDir = args.baseDataDir / args.styleName / "train"
    outputDir = args.baseDataDir / args.styleName / "output"

    print("...starting cpu-only lora training")
    print(f"...style: {args.styleName}")
    print(f"...base data dir: {args.baseDataDir}")
    print(f"...train dir: {trainDir}")
    print(f"...output dir: {outputDir}")

    if not baseModelPath.exists():
        sys.exit(f"ERROR: base model not found: {baseModelPath}")

    if not trainDir.exists():
        sys.exit(f"ERROR: training directory not found: {trainDir}")

    outputDir.mkdir(parents=True, exist_ok=True)

    command = [
        "bash",
        "-lc",
        (
            f"cd {kohyaDir} && "
            f"source ~/miniconda3/etc/profile.d/conda.sh && "
            f"conda activate {condaEnvName} && "
            f"accelerate launch --num_cpu_threads_per_process={args.cpuThreads} "
            f"train_network.py "
            f"--pretrained_model_name_or_path='{baseModelPath}' "
            f"--train_data_dir='{trainDir}' "
            f"--output_dir='{outputDir}' "
            f"--output_name='{args.styleName}_r8_512' "
            f"--caption_extension='.txt' "
            f"--resolution='512,512' "
            f"--enable_bucket "
            f"--min_bucket_reso=320 "
            f"--max_bucket_reso=768 "
            f"--bucket_reso_steps=64 "
            f"--network_module=networks.lora "
            f"--network_dim=8 "
            f"--network_alpha=8 "
            f"--train_batch_size=1 "
            f"--gradient_accumulation_steps=1 "
            f"--max_train_epochs={args.epochs} "
            f"--learning_rate=1e-4 "
            f"--text_encoder_lr=5e-5 "
            f"--unet_lr=1e-4 "
            f"--optimizer_type=AdamW "
            f"--lr_scheduler=cosine "
            f"--lr_warmup_steps=50 "
            f"--mixed_precision=no "
            f"--save_every_n_epochs=1 "
            f"--save_model_as=safetensors "
            f"--clip_skip=2"
        )
    ]

    print("...launching training")
    subprocess.run(command, check=True)
    print("...training complete")


if __name__ == "__main__":
    runTraining()
