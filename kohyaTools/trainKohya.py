#!/usr/bin/env python3
"""
trainKohya.py

LoRA training launcher for kohya_ss (sd-scripts/train_network.py).

Folder layout:
  trainingRoot/
    styleName/
      10_styleName/      <-- trainDir (instance images)
      output/            <-- outputDir

Important:
- kohya expects --train_data_dir to be the PARENT of folders that contain images,
  so we pass styleDir (NOT trainDir).
- trainDir is always: styleDir / f"10_{styleName}"

Config:
- reads/writes: ~/.config/kohya/kohyaConfig.json
- CLI overrides config for this run
- if CLI changes values, config is updated (unless --dry-run)

Training modes:
- --trainFor style  (default): trains UNet only (less identity pressure)
- --trainFor person: trains UNet + Text Encoder (better likeness; heavier)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT_CONFIG_PATH = Path.home() / ".config" / "kohya" / "kohyaConfig.json"


# ----------------------------
# config helpers
# ----------------------------

def loadConfig() -> Dict[str, Any]:
    configPath = DEFAULT_CONFIG_PATH
    configPath.parent.mkdir(parents=True, exist_ok=True)

    if not configPath.exists():
        defaultConfig: Dict[str, Any] = {
            "trainingRoot": "/mnt/myVideo/Adult/tumblrForMovie",
            "kohyaRoot": str(Path.home() / "Source" / "kohya_ss"),
            "pretrainedModel": "/mnt/models/v1-5-pruned-emaonly.safetensors",
            "numCpuThreads": 8,
        }
        configPath.write_text(json.dumps(defaultConfig, indent=2), encoding="utf-8")
        return defaultConfig

    try:
        return json.loads(configPath.read_text(encoding="utf-8"))
    except Exception:
        return {}


def saveConfig(config: Dict[str, Any]) -> None:
    configPath = DEFAULT_CONFIG_PATH
    configPath.parent.mkdir(parents=True, exist_ok=True)
    configPath.write_text(json.dumps(config, indent=2), encoding="utf-8")


def prefixFor(dryRun: bool) -> str:
    return "...[]" if dryRun else "..."


# ----------------------------
# training defaults by mode
# ----------------------------

@dataclass
class TrainingDefaults:
    networkDim: int
    networkAlpha: int
    maxTrainEpochs: int
    learningRate: float
    textEncoderLr: float
    unetLr: float
    resolution: str
    enableBucket: bool
    minBucketReso: int
    maxBucketReso: int
    bucketResoSteps: int
    clipSkip: int
    trainBatchSize: int
    gradientAccumulationSteps: int
    lrScheduler: str
    lrWarmupSteps: int
    optimizerType: str
    mixedPrecision: str
    saveEveryNEpochs: int
    saveModelAs: str
    trainUnetOnly: bool


def getDefaults(trainFor: str) -> TrainingDefaults:
    # NOTE: Your GPU is tiny (3GB) and you’ve been doing CPU training.
    # These defaults are conservative and should behave on CPU.
    if trainFor == "person":
        # stronger identity: train TE + UNet, slightly higher rank, more epochs
        return TrainingDefaults(
            networkDim=16,
            networkAlpha=16,
            maxTrainEpochs=20,
            learningRate=8e-5,
            textEncoderLr=5e-5,
            unetLr=8e-5,
            resolution="512,512",
            enableBucket=True,
            minBucketReso=320,
            maxBucketReso=768,
            bucketResoSteps=64,
            clipSkip=2,
            trainBatchSize=1,
            gradientAccumulationSteps=1,
            lrScheduler="cosine",
            lrWarmupSteps=50,
            optimizerType="AdamW",
            mixedPrecision="no",
            saveEveryNEpochs=1,
            saveModelAs="safetensors",
            trainUnetOnly=False,  # key difference
        )

    # style (default): UNet only is usually enough and less likely to “break” the base model’s faces
    return TrainingDefaults(
        networkDim=8,
        networkAlpha=8,
        maxTrainEpochs=10,
        learningRate=1e-4,
        textEncoderLr=5e-5,
        unetLr=1e-4,
        resolution="512,512",
        enableBucket=True,
        minBucketReso=320,
        maxBucketReso=768,
        bucketResoSteps=64,
        clipSkip=2,
        trainBatchSize=1,
        gradientAccumulationSteps=1,
        lrScheduler="cosine",
        lrWarmupSteps=50,
        optimizerType="AdamW",
        mixedPrecision="no",
        saveEveryNEpochs=1,
        saveModelAs="safetensors",
        trainUnetOnly=True,
    )


# ----------------------------
# core
# ----------------------------

def findTrainNetworkScript(kohyaRoot: Path) -> Path:
    # You already found it here:
    # /home/andy/Source/kohya_ss/sd-scripts/train_network.py
    candidates = [
        kohyaRoot / "sd-scripts" / "train_network.py",
        kohyaRoot / "train_network.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"train_network.py not found under: {kohyaRoot}")


def parseArgs(config: Dict[str, Any]) -> argparse.Namespace:
    defaultTrainingRoot = config.get("trainingRoot", "/mnt/myVideo/Adult/tumblrForMovie")
    defaultKohyaRoot = config.get("kohyaRoot", str(Path.home() / "Source" / "kohya_ss"))
    defaultPretrained = config.get("pretrainedModel", "/mnt/models/v1-5-pruned-emaonly.safetensors")
    defaultThreads = int(config.get("numCpuThreads", 8))

    parser = argparse.ArgumentParser(description="run kohya lora training (style/person defaults)")
    parser.add_argument("styleName", help="style/person name folder under trainingRoot (e.g. kathy)")

    parser.add_argument("--trainFor", choices=["style", "person"], default="style",
                        help="choose preset defaults (default: style)")

    parser.add_argument("--trainingRoot", default=defaultTrainingRoot,
                        help="root folder that contains styleName folders")
    parser.add_argument("--kohyaRoot", default=defaultKohyaRoot,
                        help="path to kohya_ss repo")
    parser.add_argument("--pretrainedModel", default=defaultPretrained,
                        help="path to base checkpoint .safetensors")

    parser.add_argument("--numCpuThreads", type=int, default=defaultThreads,
                        help="threads passed to accelerate for cpu training")

    # override-able training knobs (optional)
    parser.add_argument("--networkDim", type=int, default=None)
    parser.add_argument("--networkAlpha", type=int, default=None)
    parser.add_argument("--maxTrainEpochs", type=int, default=None)
    parser.add_argument("--resolution", default=None)
    parser.add_argument("--learningRate", type=float, default=None)
    parser.add_argument("--textEncoderLr", type=float, default=None)
    parser.add_argument("--unetLr", type=float, default=None)

    parser.add_argument("--dry-run", dest="dryRun", action="store_true",
                        help="print actions but do not run")

    return parser.parse_args()


def updateConfigFromArgs(config: Dict[str, Any], args: argparse.Namespace, dryRun: bool) -> None:
    prefix = prefixFor(dryRun)
    configPath = DEFAULT_CONFIG_PATH

    changed = False

    def setIfDifferent(key: str, value: Any) -> None:
        nonlocal changed
        if value is None:
            return
        if config.get(key) != value:
            config[key] = value
            changed = True

    setIfDifferent("trainingRoot", args.trainingRoot)
    setIfDifferent("kohyaRoot", args.kohyaRoot)
    setIfDifferent("pretrainedModel", args.pretrainedModel)
    setIfDifferent("numCpuThreads", args.numCpuThreads)

    if not changed:
        return

    if dryRun:
        print(f"{prefix} would update config: {configPath}")
        return

    print(f"{prefix} saving config to {configPath}")
    saveConfig(config)
    print(f"{prefix} updated config: {configPath}")


def buildTrainingCommand(
    *,
    args: argparse.Namespace,
    defaults: TrainingDefaults,
    styleDir: Path,
    outputDir: Path,
    trainNetworkPy: Path,
) -> str:
    # allow CLI overrides
    networkDim = args.networkDim if args.networkDim is not None else defaults.networkDim
    networkAlpha = args.networkAlpha if args.networkAlpha is not None else defaults.networkAlpha
    maxTrainEpochs = args.maxTrainEpochs if args.maxTrainEpochs is not None else defaults.maxTrainEpochs
    resolution = args.resolution if args.resolution is not None else defaults.resolution
    learningRate = args.learningRate if args.learningRate is not None else defaults.learningRate
    textEncoderLr = args.textEncoderLr if args.textEncoderLr is not None else defaults.textEncoderLr
    unetLr = args.unetLr if args.unetLr is not None else defaults.unetLr

    # output name: include mode + rank + resolution for easy comparison
    safeRes = resolution.replace(",", "x")
    outputName = f"{args.styleName}_{args.trainFor}_r{networkDim}_{safeRes}"

    # IMPORTANT:
    # Force CPU even if CUDA is present (you’ve had accidental GPU OOM).
    # - ACCELERATE_USE_CPU=1 helps
    # - CUDA_VISIBLE_DEVICES="" prevents torch from seeing the GPU
    envPrefix = "ACCELERATE_USE_CPU=1 CUDA_VISIBLE_DEVICES=''"

    cmd = [
        "cd", str(Path(args.kohyaRoot)),
        "&&", "source", "~/miniconda3/etc/profile.d/conda.sh",
        "&&", "conda", "activate", "kohya",
        "&&",
        envPrefix,
        "accelerate", "launch",
        f"--num_cpu_threads_per_process={args.numCpuThreads}",
        f"'{str(trainNetworkPy)}'",
        f"--pretrained_model_name_or_path='{args.pretrainedModel}'",
        f"--train_data_dir='{str(styleDir)}'",
        f"--output_dir='{str(outputDir)}'",
        f"--output_name='{outputName}'",
        "--caption_extension='.txt'",
        f"--resolution='{resolution}'",
        "--network_module=networks.lora",
        f"--network_dim={networkDim}",
        f"--network_alpha={networkAlpha}",
        f"--train_batch_size={defaults.trainBatchSize}",
        f"--gradient_accumulation_steps={defaults.gradientAccumulationSteps}",
        f"--max_train_epochs={maxTrainEpochs}",
        f"--learning_rate={learningRate}",
        f"--text_encoder_lr={textEncoderLr}",
        f"--unet_lr={unetLr}",
        f"--optimizer_type={defaults.optimizerType}",
        f"--lr_scheduler={defaults.lrScheduler}",
        f"--lr_warmup_steps={defaults.lrWarmupSteps}",
        f"--mixed_precision={defaults.mixedPrecision}",
        f"--save_every_n_epochs={defaults.saveEveryNEpochs}",
        f"--save_model_as={defaults.saveModelAs}",
        f"--clip_skip={defaults.clipSkip}",
    ]

    if defaults.enableBucket:
        cmd += [
            "--enable_bucket",
            f"--min_bucket_reso={defaults.minBucketReso}",
            f"--max_bucket_reso={defaults.maxBucketReso}",
            f"--bucket_reso_steps={defaults.bucketResoSteps}",
        ]

    # mode-specific switch
    if defaults.trainUnetOnly:
        cmd += ["--network_train_unet_only"]

    # join into a bash -lc string
    return " ".join(cmd)


def runTraining() -> None:
    config = loadConfig()
    args = parseArgs(config)
    prefix = prefixFor(args.dryRun)

    defaults = getDefaults(args.trainFor)

    trainingRoot = Path(args.trainingRoot).expanduser().resolve()
    styleDir = trainingRoot / args.styleName
    trainDir = styleDir / f"10_{args.styleName}"
    outputDir = styleDir / "output"

    kohyaRoot = Path(args.kohyaRoot).expanduser().resolve()
    trainNetworkPy = findTrainNetworkScript(kohyaRoot)

    print(f"{prefix} starting lora training")
    print(f"{prefix} style: {args.styleName}")
    print(f"{prefix} train for: {args.trainFor}")
    print(f"{prefix} training root: {trainingRoot}")
    print(f"{prefix} style dir: {styleDir}")
    print(f"{prefix} train dir: {trainDir}")
    print(f"{prefix} output dir: {outputDir}")
    print(f"{prefix} train script: {trainNetworkPy}")

    # validate folders
    if not styleDir.exists():
        raise FileNotFoundError(f"style dir not found: {styleDir}")

    if not trainDir.exists():
        raise FileNotFoundError(f"train dir not found: {trainDir} (expected 10_style folder)")

    # kohya expects styleDir contains subfolders with images
    # sanity check: ensure trainDir has at least 1 image
    images = list(trainDir.glob("*.png")) + list(trainDir.glob("*.jpg")) + list(trainDir.glob("*.jpeg")) + list(trainDir.glob("*.webp"))
    if len(images) == 0:
        raise RuntimeError(f"no training images found in: {trainDir}")

    if not args.dryRun:
        outputDir.mkdir(parents=True, exist_ok=True)

    updateConfigFromArgs(config, args, args.dryRun)

    cmdStr = buildTrainingCommand(
        args=args,
        defaults=defaults,
        styleDir=styleDir,
        outputDir=outputDir,
        trainNetworkPy=trainNetworkPy,
    )

    print(f"{prefix} training command: {cmdStr}")

    if args.dryRun:
        print(f"{prefix} training skipped (--dry-run)")
        return

    print(f"{prefix} launching training")
    subprocess.run(["bash", "-lc", cmdStr], check=True)
    print(f"{prefix} training complete")


if __name__ == "__main__":
    runTraining()
