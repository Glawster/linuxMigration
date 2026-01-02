#!/usr/bin/env python3
"""
trainKohya.py

LoRA training launcher for kohya_ss (sd-scripts/train_network.py).

Folder layout:
  trainingRoot/
    <styleName>/
      10_<styleName>/   (trainDir / instance images)
      output/           (outputDir)

Important:
  sd-scripts expects --train_data_dir to be the *parent* of folders that contain images,
  so we pass styleDir (NOT trainDir).

Config:
  Defaults are read from ~/.config/kohya/kohyaConfig.json and updated when args differ.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple


def prefixFor(dryRun: bool) -> str:
    return "...[]" if dryRun else "..."


def defaultConfigPath() -> Path:
    return Path.home() / ".config" / "kohya" / "kohyaConfig.json"


def loadConfig(configPath: Path) -> Dict[str, Any]:
    configPath.parent.mkdir(parents=True, exist_ok=True)
    if not configPath.exists():
        configPath.write_text("{}\n", encoding="utf-8")
        return {}
    text = configPath.read_text(encoding="utf-8").strip()
    if not text:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"config file is not a json object: {configPath}")
    return data


def saveConfig(configPath: Path, data: Dict[str, Any]) -> None:
    configPath.parent.mkdir(parents=True, exist_ok=True)
    configPath.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def mergeArgsWithConfig(args: argparse.Namespace, config: Dict[str, Any]) -> Tuple[argparse.Namespace, bool]:
    """
    Apply config defaults into args (only for None/unset-like values),
    then detect if args differs from config and should update config.
    """
    changed = False

    def applyDefault(key: str, attr: str) -> None:
        nonlocal changed
        if getattr(args, attr) is None and key in config:
            setattr(args, attr, config[key])

    applyDefault("trainingRoot", "trainingRoot")
    applyDefault("kohyaRoot", "kohyaRoot")
    applyDefault("pretrainedModel", "pretrainedModel")
    applyDefault("numCpuThreads", "numCpuThreads")
    applyDefault("trainFor", "trainFor")

    # Now detect differences and update config dict in-memory
    def syncBack(key: str, attr: str) -> None:
        nonlocal changed
        val = getattr(args, attr)
        if val is None:
            return
        if config.get(key) != val:
            config[key] = val
            changed = True

    syncBack("trainingRoot", "trainingRoot")
    syncBack("kohyaRoot", "kohyaRoot")
    syncBack("pretrainedModel", "pretrainedModel")
    syncBack("numCpuThreads", "numCpuThreads")
    syncBack("trainFor", "trainFor")

    return args, changed


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
    # Tuned defaults (safe-ish starting points). You can refine later.
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

    # default: style
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
    # CPU-only launch (avoid VRAM OOM issues)
    launch = (
        f"cd {kohyaRoot} && "
        f"source ~/miniconda3/etc/profile.d/conda.sh && "
        f"conda activate kohya && "
        f"CUDA_VISIBLE_DEVICES='' "
        f"accelerate launch --cpu --num_processes=1 --num_cpu_threads_per_process={numCpuThreads} "
        f"'{trainScript}' "
    )

    # IMPORTANT: pass styleDir as train_data_dir (parent of 10_style folders)
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


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="run kohya sd-scripts LoRA training")
    parser.add_argument("styleName", help="style/person name (used for folder + output name)")
    parser.add_argument("--trainingRoot", type=str, default=None, help="root containing style folders (e.g. /mnt/backup)")
    parser.add_argument("--kohyaRoot", type=str, default=None, help="path to kohya_ss repo (e.g. /home/andy/Source/kohya_ss)")
    parser.add_argument("--pretrainedModel", type=str, default=None, help="checkpoint safetensors path")
    parser.add_argument("--numCpuThreads", type=int, default=None, help="accelerate --num_cpu_threads_per_process")
    parser.add_argument("--trainFor", choices=["style", "person"], default=None, help="training preset (default: style)")
    parser.add_argument("--dry-run", dest="dryRun", action="store_true", help="print actions/command only")
    return parser.parse_args()


def runTraining() -> None:
    args = parseArgs()
    prefix = prefixFor(args.dryRun)

    configPath = defaultConfigPath()
    config = loadConfig(configPath)

    # Hard defaults if neither args nor config provide them
    if args.trainFor is None:
        args.trainFor = "style"
    if args.trainingRoot is None:
        args.trainingRoot = "/mnt/myVideo/Adult/tumblrForMovie"
    if args.kohyaRoot is None:
        args.kohyaRoot = str(Path.home() / "Source" / "kohya_ss")
    if args.pretrainedModel is None:
        args.pretrainedModel = "/mnt/models/v1-5-pruned-emaonly.safetensors"
    if args.numCpuThreads is None:
        args.numCpuThreads = 8

    args, configChanged = mergeArgsWithConfig(args, config)

    styleName = args.styleName
    trainingRoot = Path(args.trainingRoot).expanduser()
    kohyaRoot = Path(args.kohyaRoot).expanduser()
    pretrainedModel = Path(args.pretrainedModel).expanduser()

    styleDir = trainingRoot / styleName
    trainDir = styleDir / f"10_{styleName}"
    outputDir = styleDir / "output"
    trainScript = findTrainScript(kohyaRoot)

    preset = presetFor(args.trainFor)
    outputName = f"{styleName}_{args.trainFor}_r{preset.networkDim}_512x512"

    print(f"{prefix} starting lora training")
    print(f"{prefix} style: {styleName}")
    print(f"{prefix} train for: {args.trainFor}")
    print(f"{prefix} training root: {trainingRoot}")
    print(f"{prefix} style dir: {styleDir}")
    print(f"{prefix} train dir: {trainDir}")
    print(f"{prefix} output dir: {outputDir}")
    print(f"{prefix} train script: {trainScript}")

    if configChanged:
        if args.dryRun:
            print(f"{prefix} would update config: {configPath}")
        else:
            print(f"{prefix} saving config to {configPath}")
            saveConfig(configPath, config)
            print(f"{prefix} updated config: {configPath}")

    if not trainDir.exists():
        raise FileNotFoundError(f"train dir not found: {trainDir}")

    # Make sure output exists
    if args.dryRun:
        print(f"{prefix} would ensure output dir exists: {outputDir}")
    else:
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

    print(f"{prefix} training command: {commandStr}")

    if args.dryRun:
        return

    print(f"{prefix} launching training")
    subprocess.run(["bash", "-lc", commandStr], check=True)
    print(f"{prefix} training complete")


if __name__ == "__main__":
    runTraining()
