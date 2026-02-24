#!/usr/bin/env python3
"""
trainKohya.py

LoRA training launcher for kohya_ss (sd-scripts/train_network.py).

Folder layout:
  trainingRoot/
    <styleName>/
      10_<styleName>/   (trainDir / instance images)
      output/           (outputDir)

Conventions:
- config: ~/.config/kohya/kohyaConfig.json via kohyaConfig.py (no --configPath)
- logging: organiseMyProjects.logUtils.getLogger
- --dry-run: no side effects, logs stay the same, prefix indicates dry-run
"""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from kohyaConfig import loadConfig, saveConfig, getCfgValue, updateConfigFromArgs, DEFAULT_CONFIG_PATH  # type: ignore
from organiseMyProjects.logUtils import getLogger  # type: ignore


@dataclass(frozen=True)
class TrainPreset:
    networkDim: int
    networkAlpha: int
    maxTrainEpochs: int
    learningRate: float
    textEncoderLr: float
    unetLr: float
    clipSkip: int


def presetFor(trainFor: str) -> TrainPreset:
    if trainFor == "person":
        return TrainPreset(
            networkDim=16,
            networkAlpha=16,
            maxTrainEpochs=20,
            learningRate=8e-5,
            textEncoderLr=5e-5,
            unetLr=8e-5,
            clipSkip=2,
        )

    return TrainPreset(
        networkDim=8,
        networkAlpha=8,
        maxTrainEpochs=10,
        learningRate=1e-4,
        textEncoderLr=5e-5,
        unetLr=1e-4,
        clipSkip=2,
    )


def findTrainScript(kohyaRoot: Path) -> Path:
    candidate = kohyaRoot / "sd-scripts" / "train_network.py"
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"cannot find train script: {candidate}")


def buildTrainingCommand(
    kohyaRoot: Path,
    trainScript: Path,
    pretrainedModel: Path,
    styleDir: Path,
    outputDir: Path,
    outputName: str,
    numCpuThreads: int,
    preset: TrainPreset,
) -> str:
    launch = (
        f"cd {kohyaRoot} && "
        f"source ~/miniconda3/etc/profile.d/conda.sh && "
        f"conda activate kohya && "
        f"CUDA_VISIBLE_DEVICES='' "
        f"accelerate launch --cpu --num_processes=1 --num_cpu_threads_per_process={numCpuThreads} "
        f"'{trainScript}' "
    )

    args = [
        f"--pretrained_model_name_or_path='{pretrainedModel}'",
        f"--train_data_dir='{styleDir}'",
        f"--output_dir='{outputDir}'",
        f"--output_name='{outputName}'",
        "--caption_extension='.txt'",

        "--resolution='512,512'",

        "--network_module=networks.lora",

        f"--network_dim={preset.networkDim}",

        f"--network_alpha={preset.networkAlpha}",

        "--train_batch_size=1",

        "--gradient_accumulation_steps=1",

        f"--max_train_epochs={preset.maxTrainEpochs}",

        f"--learning_rate={preset.learningRate}",

        f"--text_encoder_lr={preset.textEncoderLr}",

        f"--unet_lr={preset.unetLr}",

        "--optimizer_type=AdamW",

        "--lr_scheduler=cosine",

        "--lr_warmup_steps=50",

        "--mixed_precision=no",

        "--save_every_n_epochs=1",

        "--save_model_as=safetensors",

        f"--clip_skip={preset.clipSkip}",

        "--enable_bucket",

        "--min_bucket_reso=320",

        "--max_bucket_reso=768",

        "--bucket_reso_steps=64",

    ]

    return launch + " ".join(args)


def parseArgs(cfg: Dict[str, Any]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="run kohya sd-scripts LoRA training")
    parser.add_argument("styleName", help="style/person name (used for folder + output name)")

    parser.add_argument("--training", type=str, default=getCfgValue(cfg, "trainingRoot", "/mnt/myVideo/Adult/tumblrForMovie"))
    parser.add_argument("--kohyaRoot", type=str, default=getCfgValue(cfg, "kohyaRoot", str(Path.home() / "Source" / "kohya_ss")))
    parser.add_argument("--pretrainedModel", type=str, default=getCfgValue(cfg, "pretrainedModel", "/mnt/models/v1-5-pruned-emaonly.safetensors"))
    parser.add_argument("--numCpuThreads", type=int, default=int(getCfgValue(cfg, "numCpuThreads", 8)))
    parser.add_argument("--trainFor", choices=["style", "person"], default=getCfgValue(cfg, "trainFor", "style"))

    parser.add_argument(
        "--confirm",
        action="store_true",
        help="execute changes (default is dry-run mode)",
    )

    return parser.parse_args()


def main() -> int:
    cfg = loadConfig()
    args = parseArgs(cfg)
    args.dryRun = not args.confirm
    prefix = "...[]" if args.dryRun else "..."
    logger = getLogger("trainKohya", includeConsole=True)

    updates = {
        "trainingRoot": str(args.training),
        "kohyaRoot": str(args.kohyaRoot),
        "pretrainedModel": str(args.pretrainedModel),
        "numCpuThreads": int(args.numCpuThreads),
        "trainFor": str(args.trainFor),
    }
    configChanged = updateConfigFromArgs(cfg, updates)
    if configChanged and not args.dryRun:
        saveConfig(cfg)
    if configChanged:
        logger.info("%s updated config: %s", prefix, DEFAULT_CONFIG_PATH)

    styleName = args.styleName
    trainingRoot = Path(args.training).expanduser()
    kohyaRoot = Path(args.kohyaRoot).expanduser()
    pretrainedModel = Path(args.pretrainedModel).expanduser()

    styleDir = trainingRoot / styleName
    trainDir = styleDir / f"10_{styleName}"
    outputDir = styleDir / "output"
    trainScript = findTrainScript(kohyaRoot)

    preset = presetFor(str(args.trainFor))
    outputName = f"{styleName}_{args.trainFor}_r{preset.networkDim}_512x512"

    logger.info("%s starting lora training", prefix)
    logger.info("%s style: %s", prefix, styleName)
    logger.info("%s train for: %s", prefix, args.trainFor)
    logger.info("%s training root: %s", prefix, trainingRoot)
    logger.info("%s style dir: %s", prefix, styleDir)
    logger.info("%s train dir: %s", prefix, trainDir)
    logger.info("%s output dir: %s", prefix, outputDir)
    logger.info("%s train script: %s", prefix, trainScript)

    if not trainDir.exists():
        logger.error("Train dir not found: %s", trainDir)
        return 2

    if not args.dryRun:
        outputDir.mkdir(parents=True, exist_ok=True)

    commandStr = buildTrainingCommand(
        kohyaRoot=kohyaRoot,
        trainScript=trainScript,
        pretrainedModel=pretrainedModel,
        styleDir=styleDir,
        outputDir=outputDir,
        outputName=outputName,
        numCpuThreads=int(args.numCpuThreads),
        preset=preset,
    )

    logger.info("%s training command: %s", prefix, commandStr)

    if args.dryRun:
        return 0

    logger.info("%s launching training", prefix)
    subprocess.run(["bash", "-lc", commandStr], check=True)
    logger.info("%s training complete", prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
