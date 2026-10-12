"""Video folders under a scan root and the oldest unwatched selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import os
from pathlib import Path

from suggestUnwatched.airdate import airdateOldest
from suggestUnwatched.plex import WatchRecord, watchPathKey

VIDEO_EXTENSIONS = frozenset(
    {
        ".avi",
        ".m2ts",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".ts",
        ".wmv",
    }
)
_FAR_WATCH = datetime.max.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class VideoFolder:
    """One directory that directly contains video files."""

    path: Path
    videoCount: int
    watchedCount: int
    plexCount: int
    sizeBytes: int
    oldestWatch: datetime | None
    airDate: date | None
    airDateSource: str


## folders


def folderExempt(folder: VideoFolder, root: Path, exemptShows: list[str]) -> bool:
    """Return whether the folder belongs to an exempt show."""
    names = _exemptNames(exemptShows)
    if not names:
        return False
    return bool(_pathNames(folder.path, root) & names)


def foldersScan(root: Path, records: dict[str, WatchRecord]) -> list[VideoFolder]:
    """Build one record for each directory that directly contains videos."""
    return [
        _folderBuild(folder, videos, records, root)
        for folder, videos in _videoFolders(root)
    ]


def foldersSelect(
    folders: list[VideoFolder],
    count: int,
    root: Path | None = None,
    exemptShows: list[str] | None = None,
) -> list[VideoFolder]:
    """Return up to count unwatched shows, oldest watch time then air date."""
    shows = exemptShows or []
    candidates = showsCollect(folders, root) if root is not None else folders
    unwatched = [folder for folder in candidates if _eligible(folder, root, shows)]
    unwatched.sort(key=_rankKey)
    return unwatched[:count]


def showName(folder: Path, root: Path) -> str:
    """Return the show name stored when this folder is exempted."""
    named = _seriesShow(folder, root)
    if named is not None:
        return named
    return _topName(folder, root)


def showsCollect(folders: list[VideoFolder], root: Path) -> list[VideoFolder]:
    """Roll season folders up to one record for each show."""
    grouped: dict[str, list[VideoFolder]] = {}
    order: list[str] = []
    for folder in folders:
        key = showName(folder.path, root).casefold()
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(folder)
    return [_showBuild(root, grouped[key]) for key in order]


def sizeFormat(sizeBytes: int) -> str:
    """Return a short size for a suggestion row."""
    gibibyte = 1024**3
    if sizeBytes >= gibibyte:
        return f"{sizeBytes / gibibyte:.1f} GiB"
    return f"{sizeBytes / 1024**2:.1f} MiB"


## utilities


def _airDate(
    folder: Path,
    root: Path,
    matched: list[WatchRecord],
) -> tuple[date | None, str]:
    aired = airdateOldest(folder, root)
    if aired is not None:
        return aired, "mcm"
    plexDates = [record.airedAt for record in matched if record.airedAt is not None]
    if not plexDates:
        return None, ""
    return min(plexDates).date(), "plex"


def _eligible(
    folder: VideoFolder,
    root: Path | None,
    exemptShows: list[str],
) -> bool:
    if not _unwatched(folder):
        return False
    if root is None:
        return True
    return not folderExempt(folder, root, exemptShows)


def _exemptNames(exemptShows: list[str]) -> set[str]:
    return {name.strip().casefold() for name in exemptShows if name.strip()}


def _folderBuild(
    folder: Path,
    videos: list[Path],
    records: dict[str, WatchRecord],
    root: Path,
) -> VideoFolder:
    matched = _matches(videos, records)
    aired, source = _airDate(folder, root, matched)
    watches = [record.lastViewedAt for record in matched if record.lastViewedAt]
    watched = sum(record.watched for record in matched)
    return VideoFolder(
        path=folder,
        videoCount=len(videos),
        watchedCount=watched,
        plexCount=len(matched),
        sizeBytes=_sizeTotal(videos),
        oldestWatch=min(watches) if watches else None,
        airDate=aired,
        airDateSource=source,
    )


def _matches(
    videos: list[Path],
    records: dict[str, WatchRecord],
) -> list[WatchRecord]:
    found: list[WatchRecord] = []
    for video in videos:
        record = records.get(watchPathKey(video))
        if record is not None:
            found.append(record)
    return found


def _oldestAir(folders: list[VideoFolder]) -> tuple[date | None, str]:
    dated = [folder for folder in folders if folder.airDate is not None]
    if not dated:
        return None, ""
    oldest = min(dated, key=lambda folder: (folder.airDate, folder.path.name))
    return oldest.airDate, oldest.airDateSource


def _pathNames(path: Path, root: Path) -> set[str]:
    try:
        relative = path.absolute().relative_to(root.absolute())
    except ValueError:
        relative = path
    names = {part.casefold() for part in relative.parts if part not in {".", ""}}
    names.add(root.absolute().name.casefold())
    return names


def _rankKey(folder: VideoFolder) -> tuple:
    if folder.oldestWatch is not None:
        group = 0
    elif folder.airDate is not None:
        group = 1
    else:
        group = 2
    watch = folder.oldestWatch or _FAR_WATCH
    aired = folder.airDate or date.max
    return (group, watch, aired, str(folder.path).casefold())


def _seriesShow(folder: Path, root: Path) -> str | None:
    current = folder.absolute()
    stop = root.absolute()
    while True:
        if (current / "series.xml").is_file():
            return current.name
        if current == stop or current.parent == current:
            return None
        current = current.parent


def _showBuild(root: Path, folders: list[VideoFolder]) -> VideoFolder:
    name = showName(folders[0].path, root)
    aired, source = _oldestAir(folders)
    watches = [folder.oldestWatch for folder in folders if folder.oldestWatch]
    return VideoFolder(
        path=_showPath(folders[0].path, root, name),
        videoCount=sum(folder.videoCount for folder in folders),
        watchedCount=sum(folder.watchedCount for folder in folders),
        plexCount=sum(folder.plexCount for folder in folders),
        sizeBytes=sum(folder.sizeBytes for folder in folders),
        oldestWatch=min(watches) if watches else None,
        airDate=aired,
        airDateSource=source,
    )


def _showPath(folder: Path, root: Path, name: str) -> Path:
    current = folder.absolute()
    stop = root.absolute()
    while current.name != name:
        if current == stop or current.parent == current:
            return stop
        current = current.parent
    return current


def _sizeTotal(videos: list[Path]) -> int:
    total = 0
    for video in videos:
        try:
            total += video.stat().st_size
        except OSError:
            continue
    return total


def _topName(folder: Path, root: Path) -> str:
    try:
        relative = folder.absolute().relative_to(root.absolute())
    except ValueError:
        return folder.name
    parts = [part for part in relative.parts if part not in {".", ""}]
    if parts:
        return parts[0]
    return root.name


def _unwatched(folder: VideoFolder) -> bool:
    return folder.videoCount > 0 and folder.watchedCount == 0


def _videoFolders(root: Path) -> list[tuple[Path, list[Path]]]:
    found: list[tuple[Path, list[Path]]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if not name.startswith("."))
        videos = _videosIn(Path(dirpath), filenames)
        if videos:
            found.append((Path(dirpath), videos))
    return found


def _videosIn(folder: Path, filenames: list[str]) -> list[Path]:
    return [
        folder / name
        for name in filenames
        if (folder / name).suffix.lower() in VIDEO_EXTENSIONS
    ]
