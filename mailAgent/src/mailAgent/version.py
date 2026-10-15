"""mailAgent package version helpers."""

from importlib.metadata import PackageNotFoundError, version


def applicationVersion() -> str:
    """Return the installed mailAgent version for user-facing display."""
    try:
        return version("mailAgent")
    except PackageNotFoundError:
        return "unknown"
