"""Chooser for exempting shows and refilling suggestions."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Static

from suggestUnwatched.config import configSave, exemptAdd, exemptRemove
from suggestUnwatched.folders import (
    VideoFolder,
    foldersSelect,
    showName,
    sizeFormat,
)

## view


class SuggestApp(App):
    """Mark shows exempt and show the next oldest unwatched folders."""

    TITLE = "Suggest unwatched"
    CSS = """
    Screen { layout: vertical; }
    #hint { height: 1; padding: 0 1; }
    #suggestions { height: 1fr; }
    #exempt-label { height: 1; padding: 0 1; }
    #exempt { height: 8; }
    """
    BINDINGS = [
        Binding("x", "exempt", "Exempt show"),
        Binding("u", "restore", "Restore show"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        root: Path,
        folders: list[VideoFolder],
        exemptShows: list[str],
        count: int,
        configPath: Path,
    ) -> None:
        super().__init__()
        self.root = root
        self.folders = folders
        self.exemptShows = list(exemptShows)
        self.count = count
        self.configPath = configPath
        self._visible: list[tuple[str, VideoFolder]] = []

    def compose(self) -> ComposeResult:
        """Build the suggestion table and the saved exempt list."""
        yield Header()
        yield Static(
            "x exempts the highlighted show and fills the next suggestion. "
            "u restores the highlighted exempt show.",
            id="hint",
        )
        yield DataTable(id="suggestions")
        yield Static("Exempt shows", id="exempt-label")
        yield DataTable(id="exempt")
        yield Footer()

    def on_mount(self) -> None:
        """Prepare both tables and focus the suggestions."""
        self._columnsBuild()
        self._fill()
        self.query_one("#suggestions", DataTable).focus()

    def action_exempt(self) -> None:
        """Save the highlighted show as exempt and refill the suggestions."""
        show = self._suggestionShow()
        if show is None:
            return
        if not self._save(exemptAdd(self.exemptShows, show)):
            return
        self._fill()
        self.notify(f"Exempted {show}")

    def action_restore(self) -> None:
        """Remove the highlighted exempt show and let it be suggested again."""
        show = self._exemptShow()
        if show is None:
            return
        if not self._save(exemptRemove(self.exemptShows, show)):
            return
        self._fill()
        self.notify(f"Restored {show}")

    def _columnsBuild(self) -> None:
        suggestions = self.query_one("#suggestions", DataTable)
        exempt = self.query_one("#exempt", DataTable)
        suggestions.add_columns("Show", "Aired", "Size", "Videos")
        exempt.add_column("Exempt shows")
        suggestions.cursor_type = "row"
        exempt.cursor_type = "row"

    def _exemptShow(self) -> str | None:
        table = self.query_one("#exempt", DataTable)
        row = 0 if table.cursor_row is None else table.cursor_row
        if table.row_count == 0 or row < 0 or row >= len(self.exemptShows):
            return None
        return self.exemptShows[row]

    def _fill(self) -> None:
        suggestions = self.query_one("#suggestions", DataTable)
        exempt = self.query_one("#exempt", DataTable)
        suggestions.clear()
        exempt.clear()
        self._visible = _visibleRows(
            self.folders, self.count, self.root, self.exemptShows
        )
        for show, folder in self._visible:
            suggestions.add_row(*_suggestionCells(show, folder))
        for show in self.exemptShows:
            exempt.add_row(show)

    def _save(self, shows: list[str]) -> bool:
        try:
            configSave(self.configPath, shows)
        except ValueError as error:
            self.notify(str(error), severity="error")
            return False
        self.exemptShows = shows
        return True

    def _suggestionShow(self) -> str | None:
        table = self.query_one("#suggestions", DataTable)
        row = table.cursor_row
        if row is None or row < 0 or row >= len(self._visible):
            return None
        return self._visible[row][0]


## utilities


def _aired(folder: VideoFolder) -> str:
    if folder.airDate is None:
        return "unknown"
    source = folder.airDateSource or "none"
    return f"{folder.airDate.isoformat()} {source}"


def _suggestionCells(show: str, folder: VideoFolder) -> tuple[str, ...]:
    return (
        show,
        _aired(folder),
        sizeFormat(folder.sizeBytes),
        str(folder.videoCount),
    )


def _visibleRows(
    folders: list[VideoFolder],
    count: int,
    root: Path,
    exemptShows: list[str],
) -> list[tuple[str, VideoFolder]]:
    selected = foldersSelect(folders, count, root, exemptShows)
    return [(showName(folder.path, root), folder) for folder in selected]
