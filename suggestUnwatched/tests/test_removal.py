"""The remove script quotes show paths and is not executed."""

import os
import shlex

from suggestUnwatched.folders import VideoFolder
from suggestUnwatched.removal import removalScriptPath, removalScriptWrite


def _show(path) -> VideoFolder:
    return VideoFolder(
        path=path,
        videoCount=1,
        watchedCount=0,
        plexCount=1,
        sizeBytes=1,
        oldestWatch=None,
        airDate=None,
        airDateSource="",
    )


def test_script_path_is_the_working_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    assert removalScriptPath() == tmp_path.resolve() / "removeShows.sh"


def test_script_quotes_show_paths_and_leaves_them_in_place(tmp_path) -> None:
    show = tmp_path / "It's a Show"
    show.mkdir()
    marker = show / "keep.txt"
    marker.write_text("still here", encoding="utf-8")
    script = tmp_path / "removeShows.sh"

    removalScriptWrite(script, [_show(show)])

    text = script.read_text(encoding="utf-8")
    assert f"rm -rf -- {shlex.quote(str(show))}" in text
    assert "set -euo pipefail" in text
    assert marker.read_text(encoding="utf-8") == "still here"
    assert not os.access(script, os.X_OK)


def test_empty_script_has_no_rm_command(tmp_path) -> None:
    script = tmp_path / "nested" / "removeShows.sh"

    removalScriptWrite(script, [])

    text = script.read_text(encoding="utf-8")
    assert "No shows were suggested." in text
    assert "rm -rf" not in text
