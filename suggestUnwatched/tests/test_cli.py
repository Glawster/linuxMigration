"""Command validation and the read-only suggestion report."""

from pathlib import Path
import sqlite3
import sys

import pytest

from suggestUnwatched.cli import (
    _reportLine,
    _sizeFormat,
    countRequire,
    main,
    pathRequireDirectory,
    pathRequireFile,
)
from suggestUnwatched.folders import VideoFolder


def test_count_requires_one() -> None:
    assert countRequire(5) == 5
    with pytest.raises(ValueError, match="at least 1"):
        countRequire(0)


def test_paths_must_exist(tmp_path) -> None:
    folder = tmp_path / "TV"
    folder.mkdir()
    database = tmp_path / "library.db"
    database.write_bytes(b"")

    assert pathRequireDirectory(folder) == folder.absolute()
    assert pathRequireFile(database) == database.absolute()
    with pytest.raises(ValueError, match="not a directory"):
        pathRequireDirectory(database)
    with pytest.raises(ValueError, match="not a file"):
        pathRequireFile(folder)
    with pytest.raises(ValueError, match="not a directory"):
        pathRequireDirectory(Path("/missing/suggest-unwatched"))


def _emptyDatabase(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript("""
        CREATE TABLE media_parts (
            id INTEGER, media_item_id INTEGER, file TEXT, deleted_at INTEGER
        );
        CREATE TABLE media_items (
            id INTEGER, metadata_item_id INTEGER, deleted_at INTEGER
        );
        CREATE TABLE metadata_items (
            id INTEGER, guid TEXT, originally_available_at INTEGER,
            deleted_at INTEGER
        );
        CREATE TABLE metadata_item_settings (
            id INTEGER, guid TEXT, view_count INTEGER,
            last_viewed_at INTEGER, view_offset INTEGER
        );
        """)
    connection.close()


def test_main_suggests_oldest_folder(tmp_path, monkeypatch, capsys) -> None:
    root = tmp_path / "TV"
    video = root / "Old" / "episode.mkv"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"x")
    (video.parent / "episode.xml").write_text(
        "<Item><FirstAired>1977-05-25</FirstAired></Item>",
        encoding="utf-8",
    )
    database = tmp_path / "library.db"
    _emptyDatabase(database)
    monkeypatch.setattr(
        sys,
        "argv",
        ["suggestUnwatched", str(root), "--plex-db", str(database), "--count", "5"],
    )

    main()

    captured = capsys.readouterr()
    assert "1977-05-25" in captured.err
    assert "Old" in captured.err
    assert "suggestion complete" in captured.err


def test_main_rejects_missing_root(tmp_path, monkeypatch) -> None:
    database = tmp_path / "library.db"
    database.write_bytes(b"")
    monkeypatch.setattr(
        sys,
        "argv",
        ["suggestUnwatched", str(tmp_path / "missing"), "--plex-db", str(database)],
    )

    with pytest.raises(SystemExit) as caught:
        main()

    assert caught.value.code == 1


def test_main_rejects_unreadable_library(tmp_path, monkeypatch, capsys) -> None:
    root = tmp_path / "TV"
    root.mkdir()
    database = tmp_path / "library.db"
    database.write_text("not a database", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["suggestUnwatched", str(root), "--plex-db", str(database)],
    )

    with pytest.raises(SystemExit) as caught:
        main()

    assert caught.value.code == 1
    assert "Plex library" in capsys.readouterr().err


def test_main_reports_scan_failure(tmp_path, monkeypatch) -> None:
    root = tmp_path / "TV"
    root.mkdir()
    database = tmp_path / "library.db"
    _emptyDatabase(database)
    monkeypatch.setattr(
        sys,
        "argv",
        ["suggestUnwatched", str(root), "--plex-db", str(database)],
    )

    def fail(*_args, **_kwargs):
        raise OSError("disk")

    monkeypatch.setattr("suggestUnwatched.cli.watchLoad", fail)

    with pytest.raises(SystemExit) as caught:
        main()

    assert caught.value.code == 1


def test_report_line_covers_unknown_date_and_large_size(tmp_path) -> None:
    folder = VideoFolder(
        path=Path("/elsewhere/Show"),
        videoCount=2,
        watchedCount=0,
        plexCount=0,
        sizeBytes=1024**3,
        oldestWatch=None,
        airDate=None,
        airDateSource="",
    )

    line = _reportLine(1, folder, tmp_path)

    assert line.startswith("1. /elsewhere/Show")
    assert "unknown (none)" in line
    assert _sizeFormat(folder.sizeBytes) == "1.0 GiB"
    assert _sizeFormat(1) == "0.0 MiB"


def test_main_says_when_nothing_matches(tmp_path, monkeypatch, capsys) -> None:
    root = tmp_path / "TV"
    root.mkdir()
    database = tmp_path / "library.db"
    _emptyDatabase(database)
    monkeypatch.setattr(
        sys,
        "argv",
        ["suggestUnwatched", str(root), "--plex-db", str(database)],
    )

    main()

    assert "no unwatched video folders" in capsys.readouterr().err
