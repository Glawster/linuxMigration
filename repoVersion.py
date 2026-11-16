"""The version of this repository checkout, for tool headers.

Prints the git description of the checkout against its version tags, for
example ``v1.4a2``, ``v1.4a2-4-g1a2b3c4`` (4 commits after v1.4a2) or
``v1.4a2-dirty`` (uncommitted changes). Away from a tag, a branch whose
VERSION differs from the tag it follows gives both, for example
``1.4a3 (v1.4a2-1-g1a2b3c4)``. Before the first tag it gives the VERSION file
with the commit, and without git the VERSION file alone. See
.github/additional-instructions.md ("Versioning and releases").

Usage::

    from repoVersion import repoVersion
    print(f"myTool {repoVersion()}")
"""

import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent


def repoVersion(root: Path = REPO_ROOT) -> str:
    """Return the description of the checkout at ``root``."""
    versionFile = root / "VERSION"
    fileVersion = (
        versionFile.read_text().strip() if versionFile.is_file() else "unknown"
    )
    try:
        described = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "describe",
                "--tags",
                "--match",
                "v[0-9]*",
                "--dirty",
                "--always",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return fileVersion
    if not described.startswith("v"):
        return f"{fileVersion} ({described})"
    # Away from a tag, a branch's own VERSION names the work being run.
    match = re.fullmatch(r"v(.+)-\d+-g[0-9a-f]+(-dirty)?", described)
    if match and match.group(1) != fileVersion:
        return f"{fileVersion} ({described})"
    return described


if __name__ == "__main__":
    print(repoVersion())
