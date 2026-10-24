"""The version of this repository checkout, for tool headers.

Prints the git description of the checkout against its release tags, for
example ``v1.3``, ``v1.3-4-g1a2b3c4`` (4 commits after v1.3) or
``v1.3-dirty`` (uncommitted changes). Before the first tag it gives the
VERSION file with the commit, and without git the VERSION file alone. See
.github/additional-instructions.md ("Versioning and releases").

Usage::

    from repoVersion import repoVersion
    print(f"myTool {repoVersion()}")
"""

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
    if described.startswith("v"):
        return described
    return f"{fileVersion} ({described})"


if __name__ == "__main__":
    print(repoVersion())
