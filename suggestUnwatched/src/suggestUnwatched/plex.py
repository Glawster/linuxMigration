"""Watch state from the local Plex library database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

DEFAULT_PLEX_DB = Path(
    "/var/lib/plexmediaserver/Library/Application Support/"
    "Plex Media Server/Plug-in Support/Databases/"
    "com.plexapp.plugins.library.db"
)


@dataclass(frozen=True)
class WatchRecord:
    """Plex play state for one video file."""

    watched: bool
    lastViewedAt: datetime | None
    airedAt: datetime | None


## watch


def watchLoad(database: Path, root: Path) -> dict[str, WatchRecord]:
    """Map video file paths under root to Plex watch records."""
    connection = _connect(database)
    try:
        rows = _rowsRead(connection, watchPrefix(root))
    finally:
        connection.close()
    return {
        watchPathKey(Path(path)): _recordBuild(watched, viewed, aired)
        for path, watched, viewed, aired in rows
    }


def watchPathKey(path: Path) -> str:
    """Stable absolute path key shared by the disk walk and Plex."""
    return str(path.expanduser().absolute())


def watchPrefix(root: Path) -> str:
    """SQL LIKE prefix for files inside root, with wildcards escaped."""
    text = f"{watchPathKey(root).rstrip('/')}/"
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escaped + "%"


## utilities


def _connect(database: Path) -> sqlite3.Connection:
    uri = f"{database.absolute().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _recordBuild(
    watched: int,
    viewed: int | None,
    aired: int | None,
) -> WatchRecord:
    return WatchRecord(
        watched=bool(watched),
        lastViewedAt=_timeFrom(viewed),
        airedAt=_timeFrom(aired),
    )


def _rowsRead(
    connection: sqlite3.Connection,
    prefix: str,
) -> list[tuple[str, int, int | None, int | None]]:
    return connection.execute(
        """
        SELECT
            mp.file AS file,
            MAX(
                CASE
                    WHEN COALESCE(s.view_count, 0) > 0
                      OR s.last_viewed_at IS NOT NULL
                      OR COALESCE(s.view_offset, 0) > 0
                    THEN 1
                    ELSE 0
                END
            ) AS watched,
            MIN(s.last_viewed_at) AS last_viewed_at,
            MIN(mi.originally_available_at) AS aired_at
        FROM media_parts AS mp
        JOIN media_items AS mit ON mit.id = mp.media_item_id
        JOIN metadata_items AS mi ON mi.id = mit.metadata_item_id
        LEFT JOIN metadata_item_settings AS s ON s.guid = mi.guid
        WHERE mp.deleted_at IS NULL
          AND mit.deleted_at IS NULL
          AND mi.deleted_at IS NULL
          AND mp.file LIKE ? ESCAPE '\\'
        GROUP BY mp.file
        """,
        (prefix,),
    ).fetchall()


def _timeFrom(value: int | None) -> datetime | None:
    if not value or int(value) <= 0:
        return None
    return datetime.fromtimestamp(int(value), timezone.utc)
