#!/usr/bin/env python3
"""
folderCreateAndMove.py

Given a folder, identifies common filename prefixes across files and
sub-folders, then creates a sub-folder for each prefix and moves all
matching items into it.

Usage:
    python3 folderCreateAndMove.py --folder <path>

Requires: tqdm
"""

import argparse
import os

import tqdm


def identifyCommonString(folderPath: str) -> list[str]:
    """Scan folderPath and return a list of common filename prefix strings."""
    stringList = []
    filesCount = sum(
        len(dirs) + len(files) for _, dirs, files in os.walk(folderPath)
    )

    with tqdm.tqdm(total=filesCount) as pbar:
        for root, dirs, files in os.walk(folderPath):
            for name in dirs + files:
                pbar.update(1)

                if os.path.isfile(os.path.join(root, name)):
                    name, _ = os.path.splitext(name)

                for root2, dirs2, files2 in os.walk(folderPath):
                    for name2 in dirs2 + files2:

                        if os.path.isfile(os.path.join(root2, name2)):
                            name2, _ = os.path.splitext(name2)

                        if name == name2:
                            continue

                        thisName = name.split(".")[0]
                        thisName2 = name2.split(".")[0]

                        if " - " in thisName:
                            thisName = thisName.split(" - ")[0]
                        if " - " in thisName2:
                            thisName2 = thisName2.split(" - ")[0]

                        commonString = os.path.commonprefix([thisName, thisName2])

                        if len(commonString) < 3:
                            continue

                        if commonString not in stringList:
                            stringList.append(commonString)

    return stringList


def dedupeCommonStrings(stringList: list[str]) -> list[str]:
    """Remove any string that is a substring of another string in the list."""
    result = list(stringList)
    for commonString in stringList:
        for commonString2 in stringList:
            if commonString in commonString2 and commonString != commonString2:
                try:
                    result.remove(commonString)
                except ValueError:
                    pass
    return result


def groupByCommonString(folderPath: str, stringList: list[str]) -> None:
    """Create a sub-folder for each prefix and move matching top-level items into it."""
    for commonString in stringList:
        folderName = os.path.join(folderPath, commonString)
        if not os.path.exists(folderName):
            os.makedirs(folderName)
        for fileName in os.listdir(folderPath):
            if commonString in fileName and commonString != fileName:
                os.rename(
                    os.path.join(folderPath, fileName),
                    os.path.join(folderName, fileName),
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Group files by common filename prefix into sub-folders."
    )
    parser.add_argument(
        "--folder",
        required=True,
        help="Path to the folder to organise.",
    )
    args = parser.parse_args()

    folderPath = args.folder
    stringList = identifyCommonString(folderPath)
    stringList = dedupeCommonStrings(stringList)
    groupByCommonString(folderPath, stringList)
    print(f"Done. Created {len(stringList)} group(s).")
