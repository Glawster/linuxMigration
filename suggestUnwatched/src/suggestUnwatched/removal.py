"""Shell script of rm commands for suggested shows. Never executed here."""

from __future__ import annotations

from pathlib import Path
import shlex

from suggestUnwatched.folders import VideoFolder

## removal


def removalScriptPath() -> Path:
    """Return removeShows.sh in the directory the scan was started from."""
    return Path.cwd().resolve() / "removeShows.sh"


def removalScriptWrite(path: Path, shows: list[VideoFolder]) -> Path:
    """Write an rm command for each suggested show. Do not run it."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_scriptText(shows), encoding="utf-8")
    except OSError as error:
        raise ValueError(f"Cannot write remove script: {error}") from error
    return path


## utilities


def _scriptText(shows: list[VideoFolder]) -> str:
    lines = [
        "#!/bin/bash",
        "# Shows that could be archived or deleted.",
        "# Review this file, then run it yourself. suggestUnwatched does not run it.",
        "set -euo pipefail",
    ]
    if not shows:
        lines.append("# No shows were suggested.")
    for show in shows:
        lines.append(f"rm -rf -- {shlex.quote(str(show.path))}")
    return "\n".join(lines) + "\n"
