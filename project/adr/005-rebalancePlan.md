# 005: Rebalancing through a recorded title plan

- Status: Accepted
- Date: 2026-10-23
- Requirement: [002 Rebalance local movies and TV to raid-pc](../requirements/features/002-localMediaRebalance.md)
- Related: [ADR 001](001-raidMigrationSafety.md), [ADR 006](006-migrateOnHostWithDisk.md)

## Context

Requirement 002 moves some, not all, of `/mnt/movies/Movies` and
`/mnt/video/TV` to raid-pc. `migrateToRaid` migrates whole mapping sources:
its manifest, verification, `--check` and `--remove-source` all cover every
entry under the source. The selection depends on disk usage, title age, show
status and what raid-pc already holds, so it changes over time, while a copy
that takes hours, may be interrupted, and is verified and removed later must
keep one fixed scope from start to finish.

## Decisions

1. **A rebalance mapping.** A mapping with a `rebalance` object
   (`{"targetPercent": 50}`) is planned instead of migrated whole. Its
   `type` must be `movies` or `tv`, which selects the date and eligibility
   rules. It is configured like any other mapping (source folder, mount point,
   raid-pc destination, enabled), so selection, preflight and destination
   checks are unchanged.
2. **The plan is the scope.** Planning lists the top-level title folders of the
   source, sizes them from the source manifest, and selects whole folders:
   first every eligible title already present in the destination, then the
   oldest eligible titles until the disk's projected occupancy
   (`used − planned` over `used + available`, as `df` reports it) is at or
   below the target. For a rebalance mapping, every source manifest (copy,
   verification, `--check` and removal) contains only the planned folders, so
   the rest of the pipeline, including the ADR 001 safety rules, is reused
   unchanged.
3. **Eligibility and age come from the media folders.** Movies are dated by
   the `(Year)` at the end of the folder name. Shows are dated and qualified by
   Media Center Master's `series.xml` (`<FirstAired>`, `<Status>`); only
   `Ended` shows are eligible, and a missing or unreadable `series.xml` counts
   as airing. Undated titles sort after dated ones; ties sort by name.
4. **The plan is frozen once confirmed.** A preview plans into the temporary
   work directory and records nothing. A confirmed run records the plan as
   `<name>.plan` in the state directory before copying, and every later run
   (resume, `--verify-only`, `--check`, `--remove-source`) uses that recorded
   plan, even if a show has since changed status or the disk has filled. A
   rebalance mapping without a recorded plan fails closed: `--check` is never
   SAFE and nothing can be removed.
5. **Cycles.** When a recorded plan's source content has been removed, the next
   confirmed run archives that cycle's state, manifest and plan under a
   timestamp and plans afresh. Replanning before removal means deleting the
   recorded plan by hand; the tool never discards it.
6. **No disk verdict.** A rebalance mapping never retires its disk:
   `--check` reports SAFE TO REMOVE PLANNED TITLES, it never triggers a disk
   verdict, and it never counts as covering a disk entry for another mapping.
7. **Shortfalls are reported, not hidden.** If the eligible titles cannot bring
   the disk to the target, the plan still takes them all and the preview and
   confirmed run say SHORTFALL with the projected occupancy. An ended show
   already split onto raid-pc is always planned; an airing one is reported as
   split and left alone. Lack of raid-pc space is refused by the existing space
   check.

## Consequences

- The proven copy, verify and removal code is not forked; a rebalance mapping
  differs only in its source manifest and its check subject.
- Planning reads every top-level `series.xml` and lists the destination's top
  level, so a preview costs one source scan plus one destination listing.
- The plan is only as good as Media Center Master's metadata. A show wrongly
  marked `Ended` would be moved; a show marked airing in error stays local.
- A show that resumes airing after its plan is recorded is still moved by that
  plan. New episodes written into a planned show during the move fail the
  stability check, as for any changing source.
- A title moved to raid-pc is not moved back if the local disk later empties.
