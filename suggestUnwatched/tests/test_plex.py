"""Plex watch loading uses a temporary library database."""

import sqlite3
from datetime import datetime, timezone

from suggestUnwatched.plex import watchLoad, watchPathKey


def databaseBuild(path, rows: list[tuple]) -> None:
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
    for part, item, metadata, setting in rows:
        connection.execute("INSERT INTO media_parts VALUES (?, ?, ?, ?)", part)
        connection.execute("INSERT INTO media_items VALUES (?, ?, ?)", item)
        connection.execute("INSERT INTO metadata_items VALUES (?, ?, ?, ?)", metadata)
        if setting is not None:
            connection.execute(
                "INSERT INTO metadata_item_settings VALUES (?, ?, ?, ?, ?)",
                setting,
            )
    connection.commit()
    connection.close()


def test_load_marks_played_resumed_and_ignores_deleted(tmp_path) -> None:
    root = tmp_path / "TV"
    played = root / "Played" / "episode.mkv"
    fresh = root / "Fresh" / "episode.mkv"
    resumed = root / "Resumed" / "episode.mkv"
    deleted = root / "Deleted" / "episode.mkv"
    outside = tmp_path / "elsewhere" / "episode.mkv"
    database = tmp_path / "library.db"
    aired = int(datetime(1998, 5, 6, tzinfo=timezone.utc).timestamp())
    viewed = int(datetime(2024, 2, 3, tzinfo=timezone.utc).timestamp())
    databaseBuild(
        database,
        [
            (
                (1, 1, str(played), None),
                (1, 1, None),
                (1, "played", aired, None),
                (1, "played", 1, viewed, None),
            ),
            (
                (2, 2, str(fresh), None),
                (2, 2, None),
                (2, "fresh", aired, None),
                None,
            ),
            (
                (3, 3, str(resumed), None),
                (3, 3, None),
                (3, "resumed", None, None),
                (2, "resumed", 0, None, 1200),
            ),
            (
                (4, 4, str(deleted), 1),
                (4, 4, None),
                (4, "deleted", aired, None),
                None,
            ),
            (
                (5, 5, str(outside), None),
                (5, 5, None),
                (5, "outside", aired, None),
                None,
            ),
        ],
    )

    records = watchLoad(database, root)

    assert set(records) == {
        watchPathKey(played),
        watchPathKey(fresh),
        watchPathKey(resumed),
    }
    assert records[watchPathKey(played)].watched is True
    assert records[watchPathKey(played)].lastViewedAt == datetime.fromtimestamp(
        viewed, timezone.utc
    )
    assert records[watchPathKey(fresh)].watched is False
    assert records[watchPathKey(fresh)].airedAt == datetime.fromtimestamp(
        aired, timezone.utc
    )
    assert records[watchPathKey(resumed)].watched is True
