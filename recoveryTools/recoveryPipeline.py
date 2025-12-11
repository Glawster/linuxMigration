#!/usr/bin/env python3
import subprocess
from pathlib import Path

BASE = Path("/mnt/games1/Recovery")

def run(cmd):
    print(">>", " ".join(str(x) for x in cmd))
    subprocess.check_call(cmd)

def main():
    # 1) filter black images
    run(["python", "filterBlackImages.py"])

    # 2) perceptual dedupe
    run(["python", "dedupeImages.py"])

    # 3) sort images by resolution
    run(["python", "sortImagesByResolution.py"])

    # 4) build image timeline
    run(["python", "buildImageTimeline.py"])

    # 5) sort videos by duration
    run(["python", "sortVideosByDuration.py"])

if __name__ == "__main__":
    main()
