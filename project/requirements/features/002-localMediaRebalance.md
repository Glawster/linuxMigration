# 002: Rebalance local movies and TV to raid-pc

## Status

ToDo

## Outcome

As the owner of andy-pc, I need the oldest movies and ended TV shows moved
from the local `/mnt/movies` and `/mnt/video` disks to the raid-pc pool until
each local disk is at most 50% occupied, without any show ever being split
between andy-pc and raid-pc, so that the local disks keep room for new media
and every title lives in exactly one store.

## Context

- `/mnt/movies` (`/mnt/movies/Movies`) and `/mnt/video` (`/mnt/video/TV`) are
  internal 4 TB SATA disks that stay on andy-pc (requirement 001). On
  2026-10-22 they were 94% and 98% occupied.
- raid-pc is the bulk store. Moved titles go into the shared pool folders
  `/mnt/storage/Movies` and `/mnt/storage/TV`, which already hold the content
  migrated by requirement 001.
- `/mnt/video` also holds `linuxBackup`, `toFile`, `Downloads`, `eBooks` and
  `Torrents`. Only `TV` is moved off `/mnt/video`. `linuxBackup` (1.3 TB) is
  moved by hand to one of the retired 4 TB USB disks; without that, `/mnt/video`
  cannot reach 50% from TV alone.
- Sonarr (on tv-pc, through the `/mnt/video` NFS export) keeps filing new
  episodes of airing shows locally, so airing shows stay local; moving one
  would split it again with the next episode.
- Media Center Master writes `series.xml` in each show folder, with `<Status>`
  (`Continuing`, `Ended`, `Upcoming`) and `<FirstAired>`. Movie folders are
  named `Title (Year)`.
- Approximate need on 2026-10-22: about 1.6 TiB of movies, and about 0.5 TiB
  of TV once `linuxBackup` has gone. raid-pc has about 3.1 TiB free once the
  requirement 001 migrations finish.

## Scope

- Selecting what moves:
  - The unit of transfer is a whole title folder: one movie folder in
    `/mnt/movies/Movies`, or one show folder in `/mnt/video/TV`.
  - A show is eligible only when its status is `Ended`. A show whose status is
    anything else, or is missing or unreadable, is treated as airing and stays
    local.
  - Oldest first: movies by the year in the folder name, shows by first-aired
    date; ties by folder name. A title without a readable date is selected
    after every dated title.
  - Titles are selected until the disk's projected occupancy is at or below
    50%, measured from the real filesystem usage at planning time.
  - A title that already exists in the raid-pc pool folder is always selected,
    whatever its age, so it is reunited on raid-pc.
- Moving uses the requirement 001 pipeline unchanged: preview by default,
  copy and verify with `--confirm`, then `--check` and an explicit
  `--remove-source` that deletes only the moved title folders.
- A preview of the plan: each selected title with its size, date and reason,
  the projected occupancy of the local disk, raid-pc free space afterwards, and
  any shortfall.
- Re-running the plan later, when the disks have refilled or more shows have
  ended.
- Automated tests and user documentation.

## Out of scope

- Moving anything from `/mnt/video` other than `TV`, including moving
  `linuxBackup` to a USB disk.
- Moving titles back from raid-pc to andy-pc.
- Updating the Media Center Master, Sonarr or Radarr libraries for the new
  paths; the owner rescans or repoints them.
- Refreshing show status from Sonarr or online sources; the `series.xml`
  status is authoritative.
- Deduplicating or renaming titles.

## Acceptance criteria

1. Given a local disk above 50%, when the plan is previewed, then it lists
   whole title folders, oldest first, until the projected occupancy is at or
   below 50%, and nothing is copied, deleted or recorded.
2. Given a show whose `series.xml` status is not `Ended`, or has no readable
   `series.xml`, when the plan is made, then the show is never selected and
   stays entirely local.
3. Given a title folder that already exists in the raid-pc pool folder, when
   the plan is made, then it is selected regardless of age, and the preview
   says why. A show in both places that is still airing is not moved and is
   reported as split.
4. Given the plan, then no show folder is ever partly selected, and after the
   move and removal every show folder exists in exactly one store.
5. Given a local disk already at or below 50%, when the plan is made, then
   nothing from that disk is selected.
6. Given that the eligible titles are not enough to reach 50%, or that raid-pc
   lacks the space for them, when the plan is previewed, then the shortfall is
   reported and no partial plan is applied silently.
7. Given `/mnt/video`, when the plan is made, then only folders under `TV` are
   ever selected.
8. Given a confirmed move, when it runs, then copy, verification, `--check` and
   `--remove-source` behave as in requirement 001, and removal deletes only the
   selected title folders, never the rest of `Movies` or `TV`, nor the mount
   point.
9. Given a movie whose folder name has no year, or a show whose `series.xml`
   has no first-aired date, when the plan is made, then it is ordered after
   every dated title of the same kind.
10. Given the plan is re-run after a move, when the disks have not refilled,
    then nothing is selected.

## Dependencies and decisions

- [001 raid-pc storage migration](001-raidMigration.md): the copy, verify,
  check and removal pipeline, and its safety model
  ([ADR 001](../../adr/001-raidMigrationSafety.md),
  [ADR 004](../../adr/004-migrateOnlyOnAndyPc.md)).
- Pending ADR: how the plan feeds the pipeline (for example, a generated
  include-list mapping per disk) and how per-title removal is checked when the
  local disk is not being retired.
- Prerequisites for the real run: the requirement 001 raid-pc migrations have
  finished, and `linuxBackup` has been moved off `/mnt/video`.

## Verification

- `linuxBootstrap/tests/migrateToRaidTests.sh` covers every acceptance
  criterion, using temporary directories with fake show and movie folders,
  `series.xml` fixtures and a free-space double.
- Review the real plan preview before the first confirmed move, checking that
  no airing show is selected and that the projected occupancy is at or below
  50%.

## Change history

- 2026-10-22: created from the owner's brief: move local TV or movies to raid
  until the local disks are 50% occupied, oldest first, without splitting a
  show; airing shows stay local; only `TV` moves off `/mnt/video`, and
  `linuxBackup` goes to a USB disk by hand.
