#!/usr/bin/env python3
"""
recoveryPipeline.py

Pipeline to process images in place:
1. Filter out black/invalid images
2. Deduplicate images using perceptual hashing

Both operations preserve directory structure and create subfolders
(BlackImages/ and Duplicates/) within the source directory.
"""

import argparse
import subprocess
from pathlib import Path

def run(cmd):
    print(">>", " ".join(str(x) for x in cmd))
    subprocess.check_call(cmd)

def main():
    parser = argparse.ArgumentParser(
        description="Run recovery pipeline: filter black images and deduplicate in place."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source directory to process",
    )
    args = parser.parse_args()

    try:
        sourceDir = Path(args.source).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as e:
        raise SystemExit(f"Error resolving source directory path: {e}")
    
    if not sourceDir.is_dir():
        raise SystemExit(f"Source directory does not exist: {sourceDir}")

    print(f"Processing images in: {sourceDir}")
    print()

    # 1) filter black images
    print("Step 1: Filtering black/invalid images...")
    run(["python3", "filterBlackImages.py", "--source", str(sourceDir)])
    print()

    # 2) perceptual dedupe
    print("Step 2: Deduplicating images...")
    run(["python3", "dedupeImages.py", "--source", str(sourceDir)])
    print()

    print("Pipeline complete!")

if __name__ == "__main__":
    main()
