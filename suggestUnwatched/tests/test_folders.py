"""Folder selection prefers unwatched folders and oldest known dates."""

from datetime import date, datetime, timezone

from suggestUnwatched.folders import (
    VideoFolder,
    foldersScan,
    foldersSelect,
    showName,
)
from suggestUnwatched.plex import WatchRecord, watchPathKey


def _folder(path, **overrides) -> VideoFolder:
    values = dict(
        path=path,
        videoCount=1,
        watchedCount=0,
        plexCount=1,
        sizeBytes=1,
        oldestWatch=None,
        airDate=None,
        airDateSource="",
    )
    values.update(overrides)
    return VideoFolder(**values)


def test_select_skips_watched_and_orders_by_air_date(tmp_path) -> None:
    watched = tmp_path / "Watched" / "Season 1" / "episode.mkv"
    older = tmp_path / "Older" / "Season 1" / "episode.mkv"
    newer = tmp_path / "Newer" / "Season 1" / "episode.mkv"
    for video in (watched, older, newer):
        video.parent.mkdir(parents=True)
        video.write_bytes(b"video")
    for folder, aired in (
        (watched.parent, "1970-01-01"),
        (older.parent, "1981-02-03"),
        (newer.parent, "2010-06-07"),
    ):
        metadata = folder / "metadata"
        metadata.mkdir()
        (metadata / "episode.xml").write_text(
            f"<Item><FirstAired>{aired}</FirstAired></Item>",
            encoding="utf-8",
        )
    records = {
        watchPathKey(watched): WatchRecord(
            watched=True,
            lastViewedAt=datetime(2024, 1, 1, tzinfo=timezone.utc),
            airedAt=None,
        )
    }

    selected = foldersSelect(foldersScan(tmp_path, records), 5)

    assert [folder.path for folder in selected] == [older.parent, newer.parent]
    assert selected[0].airDate == date(1981, 2, 3)
    assert selected[0].airDateSource == "mcm"
    assert selected[0].sizeBytes == len(b"video")


def test_select_uses_plex_air_date_when_mcm_is_missing(tmp_path) -> None:
    video = tmp_path / "Loose" / "episode.mp4"
    video.parent.mkdir()
    video.write_bytes(b"x")
    aired = datetime(1999, 3, 4, tzinfo=timezone.utc)
    records = {
        watchPathKey(video): WatchRecord(
            watched=False,
            lastViewedAt=None,
            airedAt=aired,
        )
    }

    selected = foldersSelect(foldersScan(tmp_path, records), 1)

    assert selected[0].airDate == date(1999, 3, 4)
    assert selected[0].airDateSource == "plex"


def test_select_ranks_watch_time_before_air_date(tmp_path) -> None:
    early = _folder(
        tmp_path / "early",
        oldestWatch=datetime(2001, 1, 1, tzinfo=timezone.utc),
        airDate=date(2020, 1, 1),
    )
    aired = _folder(tmp_path / "aired", airDate=date(1950, 1, 1))
    unknown = _folder(tmp_path / "unknown")

    selected = foldersSelect([unknown, aired, early], 3)

    assert [folder.path.name for folder in selected] == ["early", "aired", "unknown"]


def test_select_skips_exempt_show_and_keeps_the_next(tmp_path) -> None:
    thunderbirds = _folder(
        tmp_path / "Thunderbirds" / "Season 1",
        airDate=date(1965, 9, 30),
    )
    making = _folder(
        tmp_path / "Thunderbirds" / "Making Of",
        airDate=date(1965, 9, 1),
    )
    kept = _folder(tmp_path / "Firefly" / "Season 1", airDate=date(2002, 9, 20))
    show = tmp_path / "Thunderbirds"
    show.mkdir(parents=True)
    (show / "series.xml").write_text(
        "<Series><FirstAired>1965-09-30</FirstAired></Series>",
        encoding="utf-8",
    )

    selected = foldersSelect(
        [making, thunderbirds, kept],
        1,
        tmp_path,
        ["thunderbirds"],
    )

    assert [folder.path for folder in selected] == [tmp_path / "Firefly"]
    assert showName(thunderbirds.path, tmp_path) == "Thunderbirds"


def test_select_rolls_seasons_into_the_show(tmp_path) -> None:
    first = _folder(
        tmp_path / "UFO" / "Season 1",
        airDate=date(1970, 9, 16),
        sizeBytes=10,
        videoCount=2,
    )
    second = _folder(
        tmp_path / "UFO" / "Season 2",
        airDate=date(1971, 1, 1),
        sizeBytes=30,
        videoCount=4,
    )
    watched = _folder(
        tmp_path / "Firefly" / "Season 1",
        airDate=date(1960, 1, 1),
        watchedCount=1,
    )

    selected = foldersSelect([second, first, watched], 5, tmp_path, [])

    assert [folder.path.name for folder in selected] == ["UFO"]
    assert selected[0].videoCount == 6
    assert selected[0].sizeBytes == 40
    assert selected[0].airDate == date(1970, 9, 16)


def test_show_name_uses_first_directory_without_series_xml(tmp_path) -> None:
    folder = tmp_path / "UFO" / "Season 1"
    folder.mkdir(parents=True)

    assert showName(folder, tmp_path) == "UFO"


def test_scan_ignores_hidden_directories(tmp_path) -> None:
    hidden = tmp_path / ".hidden" / "episode.mkv"
    hidden.parent.mkdir()
    hidden.write_bytes(b"x")

    assert foldersScan(tmp_path, {}) == []


def test_scan_keeps_folder_with_no_air_date(tmp_path) -> None:
    video = tmp_path / "Undated" / "episode.mkv"
    video.parent.mkdir()
    video.write_bytes(b"x")
    broken = video.parent / "missing.mkv"
    broken.symlink_to(tmp_path / "absent.mkv")

    found = foldersScan(tmp_path, {})

    assert found[0].airDate is None
    assert found[0].airDateSource == ""
    assert found[0].sizeBytes == 1
    assert found[0].videoCount == 2
