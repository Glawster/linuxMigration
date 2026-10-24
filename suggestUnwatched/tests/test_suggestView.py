"""The chooser exempts a show and fills the next suggestion."""

import asyncio
from datetime import date

from textual.widgets import DataTable

from suggestUnwatched.config import configLoad
from suggestUnwatched.folders import VideoFolder
from suggestUnwatched.suggestView import SuggestApp


def _folder(path, aired: date) -> VideoFolder:
    return VideoFolder(
        path=path,
        videoCount=3,
        watchedCount=0,
        plexCount=3,
        sizeBytes=2048,
        oldestWatch=None,
        airDate=aired,
        airDateSource="mcm",
    )


def test_exempt_and_restore_refill_the_suggestion(tmp_path) -> None:
    root = tmp_path / "TV"
    folders = [
        _folder(root / "Thunderbirds" / "Season 1", date(1965, 9, 30)),
        _folder(root / "UFO" / "Season 1", date(1970, 9, 16)),
        _folder(root / "Firefly" / "Season 1", date(2002, 9, 20)),
    ]
    config = tmp_path / "config.json"
    app = SuggestApp(root, folders, [], 1, config)

    async def run() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            suggestions = app.query_one("#suggestions", DataTable)
            assert suggestions.get_row_at(0)[0] == "Thunderbirds"
            await pilot.press("x")
            await pilot.pause()
            assert suggestions.get_row_at(0)[0] == "UFO"
            assert configLoad(config) == ["Thunderbirds"]
            await pilot.press("u")
            await pilot.pause()
            assert suggestions.get_row_at(0)[0] == "Thunderbirds"
            assert configLoad(config) == []

    asyncio.run(run())
