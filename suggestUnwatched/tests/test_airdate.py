"""MCM air-date parsing uses fictional metadata fixtures."""

from datetime import date
from pathlib import Path

from suggestUnwatched.airdate import airdateOldest, airdateParse


def test_parse_accepts_iso_and_day_month_year() -> None:
    assert airdateParse("2003-10-28") == date(2003, 10, 28)
    assert airdateParse("16/09/2020 extra") == date(2020, 9, 16)


def test_parse_rejects_placeholder_dates() -> None:
    assert airdateParse("0001-01-01") is None
    assert airdateParse("") is None
    assert airdateParse("not-a-date") is None


def test_oldest_uses_episode_metadata_before_series(tmp_path) -> None:
    show = tmp_path / "Show"
    season = show / "Season 1"
    metadata = season / "metadata"
    metadata.mkdir(parents=True)
    (show / "series.xml").write_text(
        "<Series><FirstAired>1990-01-01</FirstAired></Series>",
        encoding="utf-8",
    )
    (metadata / "episode.xml").write_text(
        "\ufeff<Item><FirstAired>2001-05-04</FirstAired></Item>",
        encoding="utf-8",
    )
    (season / "later.xml").write_text(
        "<Item><FirstAired>2002-01-01</FirstAired></Item>",
        encoding="utf-8",
    )

    assert airdateOldest(season, tmp_path) == date(2001, 5, 4)


def test_oldest_falls_back_to_parent_series(tmp_path) -> None:
    show = tmp_path / "Show"
    season = show / "Season 1"
    season.mkdir(parents=True)
    (show / "series.xml").write_text(
        "<Series><FirstAired>1984-09-16</FirstAired></Series>",
        encoding="utf-8",
    )

    assert airdateOldest(season, tmp_path) == date(1984, 9, 16)


def test_oldest_ignores_xml_without_a_date(tmp_path) -> None:
    folder = tmp_path / "Season 1"
    folder.mkdir()
    (folder / "note.xml").write_text(
        "<Item><Title>Nope</Title></Item>", encoding="utf-8"
    )

    assert airdateOldest(folder, tmp_path) is None


def test_oldest_skips_unreadable_xml(tmp_path, monkeypatch) -> None:
    folder = tmp_path / "Season 1"
    folder.mkdir()
    blocked = folder / "blocked.xml"
    blocked.write_text(
        "<Item><FirstAired>1991-01-01</FirstAired></Item>", encoding="utf-8"
    )
    original = Path.read_text

    def fail(self, *args, **kwargs):
        if self.name == "blocked.xml":
            raise OSError("denied")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fail)

    assert airdateOldest(folder, tmp_path) is None
