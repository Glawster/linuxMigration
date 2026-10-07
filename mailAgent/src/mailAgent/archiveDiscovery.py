"""Inspect local Thunderbird mbox or nested Maildir taxonomy without writes."""

from pathlib import Path

METADATA_SUFFIXES = {
    ".msf",
    ".dat",
    ".sqlite",
    ".sqlite-wal",
    ".sqlite-shm",
    ".json",
    ".log",
}

## discovery


def archiveDiscover(root: Path, formatName: str = "thunderbird") -> dict:
    """Return canonical paths and physical storage, retaining discovery issues."""
    if formatName not in ("thunderbird", "maildir"):
        raise ValueError("Unsupported archive format")
    result = dict(
        root=str(root),
        format=formatName,
        folders=[],
        issues=[],
        available=False,
        complete=True,
    )
    if root.is_symlink() or not root.is_dir():
        result["issues"].append(
            "Archive root missing, not a directory, or a symbolic link"
        )
        return result
    result["available"] = True
    _directoryDiscover(root, (), result)
    return result


## utilities


def _directoryDiscover(directory: Path, parts: tuple, result: dict) -> None:
    try:
        if result["format"] == "maildir" and all(
            (directory / key).is_dir() and not (directory / key).is_symlink()
            for key in ("cur", "new", "tmp")
        ):
            result["folders"].append(
                dict(
                    path="/".join(parts) or "INBOX",
                    storage=str(directory),
                    selectable=True,
                )
            )
        for entry in sorted(directory.iterdir()):
            _entryInspect(entry, parts, result)
    except OSError:
        result["complete"] = False
        result["issues"].append("Cannot read archive directory: " + str(directory))


def _entryInspect(entry: Path, parts: tuple, result: dict) -> None:
    if entry.is_symlink():
        result["issues"].append("Skipped symbolic link: " + str(entry))
        return
    if entry.name.startswith(".") or entry.suffix in METADATA_SUFFIXES:
        return
    if result["format"] == "maildir":
        if entry.is_dir() and entry.name not in ("cur", "new", "tmp"):
            _directoryDiscover(entry, (*parts, entry.name), result)
    elif entry.is_dir() and entry.name.endswith(".sbd"):
        canonical = (*parts, entry.name[:-4])
        if not (entry.parent / entry.name[:-4]).is_file():
            result["folders"].append(
                dict(path="/".join(canonical), storage=str(entry), selectable=False)
            )
        _directoryDiscover(entry, canonical, result)
    elif entry.is_file():
        with entry.open("rb") as stream:
            prefix = stream.read(5)
        if not prefix or prefix == b"From ":
            result["folders"].append(
                dict(
                    path="/".join((*parts, entry.name)),
                    storage=str(entry),
                    selectable=True,
                )
            )
        else:
            result["issues"].append("Unrecognized archive file: " + str(entry))
