# 004: Suggest unwatched video folders

## Status

Completed

## Outcome

As the owner of the media library, I need the oldest unwatched shows and
movies under a folder suggested, with a way to exempt ones I want to keep, so
that I can free disk space by removing content that is unlikely to be watched.

## Context

- Watched state comes from the local Plex library database, which this login
  can read; Media Center Master and WD TV watched markers are not used.
- Air dates come from Media Center Master episode XML and `series.xml`, with
  Plex `originally_available_at` as a fallback.
- The tool is a separate Python package with its own conda environment
  (`suggestUnwatched/environment.yml`, Textual for the chooser). It keeps the
  `src/` layout so the `suggestUnwatched` package cannot be shadowed by its
  project folder of the same name at the repository root.
- Guide: [suggestUnwatched](../../../suggestUnwatched/suggestUnwatchedIndex.md),
  [ranking](../../../suggestUnwatched/documentation/ranking.md).

## Scope

- `suggestUnwatched [root] [--report] [--count N] [--plex-db PATH]`.
- Scanning folders that directly contain video files, rolled up to one row per
  show.
- Ranking by oldest Plex last-viewed time, then oldest first-aired date, then
  oldest Plex availability date.
- An interactive chooser: `x` exempts a show (saved in
  `~/.config/suggestUnwatched/config.json`), `u` restores one, `q` quits.
- On exit, writing `rm` commands for the remaining suggestions to
  `removeShows.sh` in the starting folder, for review.
- Reporting the repository version at start-up.

## Out of scope

- Moving, deleting or running the removal script; the tool never removes
  anything.
- Writing to Plex or to media manager metadata.

## Acceptance criteria

1. Given folders where any video file has a Plex view count, last-viewed time
   or resume offset, when suggestions are made, then that whole show is not
   suggested; files not in Plex count as unwatched.
2. Given unwatched shows, when suggestions are made, then they are ordered by
   oldest last-viewed time, then oldest first-aired date, then oldest Plex
   availability date, limited to `--count` (default 5).
3. Given a show name in `exemptShows`, when suggestions are made, then no
   folder whose path contains that name is suggested, and the next oldest
   eligible folder fills its place.
4. Given `--report` or no terminal, when the command runs, then the list is
   printed and the chooser is not opened.
5. Given the chooser closes, when shows are still suggested, then they are
   listed and written as `rm` commands to `removeShows.sh`, which is not run.
6. Given a missing root, an unreadable Plex database or a count below one,
   when the command runs, then it stops with an error.
7. Given any run, when it starts, then it logs the repository version.

## Dependencies and decisions

- [ADR 008: One version and release tag for the whole repository](../../adr/008-repositoryVersion.md)
  (version reporting).

## Verification

- `conda run -n suggestUnwatched python -m pytest suggestUnwatched`: 32 tests
  covering air dates, the CLI, configuration, folder scanning and ranking,
  Plex watch state, the removal script and the chooser.

## Change history

- 2026-10-12: implemented on the `suggest-unwatched` branch.
- 2026-10-24: recorded as completed when merged to `main`; `.coverage`
  removed, guide renamed to `suggestUnwatchedIndex.md`, and the repository
  version logged at start-up.
