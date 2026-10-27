# 010: Quick verification is enough to remove replaceable media

- Status: Accepted
- Date: 2026-10-27
- Requirement: [001 raid-pc storage migration](../requirements/features/001-raidMigration.md)
- Related: [ADR 001](001-raidMigrationSafety.md)
- Amends: [ADR 001](001-raidMigrationSafety.md) decision 3

## Context

ADR 001 made a full checksum verification the condition for every disk to be
safe to remove. Checksums are read from both disks in full, so verifying the
3.4 TiB `movie2` and 3.6 TiB `video3` disks takes 10 to 11 hours each, and the
disk read speed, not the checksum tool, sets that time. Movies and TV shows
can be downloaded again if a copy turns out to be damaged; home video and
photos cannot. rsync already checks every file's whole-file checksum while it
copies; a full verification adds a second read of the data at rest.

## Decisions

1. **The required level is set per type.** `removalVerify` maps a mapping type
   to `quick` or `full`. A type that is not listed needs `full`, so without the
   setting ADR 001 behaviour is unchanged.
2. **The template accepts quick for `movies` and `tv`.** Personal types
   (`video`, `pictures`, `files`) keep requiring checksums.
3. **Nothing else about SAFE changes.** A quick verification compares every
   entry's path, type, size and modification time on both machines.
   `--check` still rescans the source and destination and still requires the
   protection check, and `--remove-source` still requires a SAFE check.
4. **The verdict states its basis.** A quick-verified copy reports
   `COPY VERIFIED (quick: removalVerify accepts it for <type>)`, so it is not
   mistaken for a checksum-verified one.

## Consequences

- Replaceable disks can be retired the same day they are copied.
- Silent corruption of a movie or TV file on raid-pc after rsync wrote it
  would not be detected before the source is removed; the remedy is to
  download the title again. SnapRAID parity on raid-pc remains the protection
  for data at rest.
- Rebalance mappings (`moviesRebalance`, `tvRebalance`) are movies and TV, so
  they also accept quick verification.
- `--verify full` stays available for any mapping and is still recorded as
  such.
