#!/usr/bin/env python3
from pathlib import Path
import shutil

srcRoot = Path.home() / "Recovery"
dstRoot = Path.home() / "RecoveryFlat"

def main():
    dstRoot.mkdir(exist_ok=True)
    count = 0
    for path in srcRoot.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in [".jpg", ".jpeg", ".mp4"]:
            continue
        target = dstRoot / path.name
        i = 1
        while target.exists():
            target = dstRoot / f"{path.stem}_{i}{path.suffix}"
            i += 1
        shutil.move(str(path), str(target))
        count += 1

    print(f"Moved {count} files into {dstRoot}")

if __name__ == "__main__":
    main()
