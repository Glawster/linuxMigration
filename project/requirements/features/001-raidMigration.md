# 001: raid-pc storage migration

## Status

InProgress

## Outcome

As the owner of andy-pc, I need to migrate my media and file storage to the
raid-pc storage pool, one source at a time, with independently verified copies
and an unambiguous answer on whether each old disk can be removed. This lets
disks be retired without risking irreplaceable multi-terabyte data.

Priorities, in order: safety, auditability, resumability, speed, convenience.

## Context

- andy-pc holds media on several mostly 4 TB NTFS disks, several nearly full:
  `/mnt/movie1`, `/mnt/movie2`, `/mnt/video1`–`/mnt/video3`, `/mnt/myVideo`,
  `/mnt/music`, `/mnt/myPictures` (and `/mnt/home`, `/mnt/games1`,
  `/mnt/games2`).
- raid-pc is the new central storage server: a mergerFS pool of 4 TB data disks
  that grows over time, with SnapRAID parity added once more disks arrive via an
  HBA. During the initial phase there may be no parity at all.
- The raid-pc pool has no per-disk numbering: sources merge into shared folders
  such as `<pool>/Movies` (movie1, movie2) and `<pool>/TV` (video1–video3 and
  `/mnt/myVideo/TV`). Final paths are not yet confirmed.
- Transfers run for many hours over the LAN and may be interrupted. Some sources
  are written to while in use (for example `/mnt/video2` by tv-pc).
- The tool is implemented in `linuxBootstrap/`
  ([guide](../../../linuxBootstrap/documentation/migrateToRaid.md)).

## Scope

- A Bash command, `migrateToRaid`, run on andy-pc.
- JSON configuration of mappings, separate from the implementation. Each
  mapping has a name, label and type, can be enabled individually, may share a
  destination with other mappings, and may migrate a folder inside a mounted
  disk.
- A preview by default, and copying with rsync over SSH only with `--confirm`.
- Selection by `--all`, `--source NAME` and `--type TYPE`.
- Pre-flight checks, classification of destination collisions, resumable
  transfer, separate quick or full verification, final source-stability
  checks, persistent state and audit logs.
- `--status`, `--check` (COPY VERIFIED and SAFE / NOT SAFE TO REMOVE, per
  mapping and per disk) and explicit `--remove-source`.
- Automated tests and user documentation.

## Out of scope

- Deciding or provisioning the raid-pc storage layout, mergerFS or SnapRAID.
- Deduplicating media or reorganising library folder structures.
- Two-way synchronisation, or updating destination files that differ from the
  source.
- Migrating ownership metadata (the remote user is not root).

## Acceptance criteria

1. Given the template configuration, when it is loaded, then every mapping is
   disabled, destinations are placeholders, and placeholders are refused before
   any network or data operation.
2. Given no `--confirm`, when a mapping is selected, then the source,
   destination, reachability, size, available space, entries to copy,
   identical entries, conflicts and the rsync command are shown, and no data or
   state changes.
3. Given a mount-point directory with no filesystem mounted, when a migration,
   check or removal runs, then it is refused and nothing is copied or recorded.
4. Given an unreachable raid-pc, an unmounted pool, a destination outside the
   pool, an unwritable destination, missing remote tools or insufficient free
   space, when a migration runs, then that mapping stops before any transfer.
5. Given destination entries that already exist, when a migration runs, then
   missing entries are copied, identical entries are skipped, and differing
   entries are recorded as conflicts and never overwritten.
6. Given an interrupted transfer, when the migration is re-run, then the partial
   data resumes from a dedicated partial directory, no partial file ever
   appears at a destination path, and the interruption is not treated as a
   conflict or as success.
7. Given files added to the source during a copy, when the copy pass ends, then
   a final synchronisation pass copies them before verification.
8. Given a completed copy, when `--verify quick` or `--verify full` runs, then
   every entry is compared by type, size and modification time (and for full,
   by checksum on both machines), with visible progress, and any mismatch fails
   verification.
9. Given a source that changes during verification or after it, when the
   migration or `--check` runs, then the result is not verified and NOT SAFE.
10. Given a different filesystem mounted at a migrated mount point, when any
    operation runs, then it is refused because the recorded UUID and mount
    point do not match.
11. Given a full verification of the current source, when `--check` runs, then
    it reports COPY VERIFIED, and SAFE TO REMOVE only if the configured raid-pc
    protection check also passes. Otherwise it reports NOT SAFE with reasons.
    Quick verification is never SAFE.
12. Given mappings that cover parts of a disk, when `--check` runs, then the
    disk is SAFE only when every mapping on it is SAFE and every top-level
    entry belongs to a mapping. Overlapping mappings are rejected.
13. Given `--remove-source`, when the check is not SAFE, the confirmation is
    missing, or the run is not interactive without `--yes-delete`, then
    nothing is deleted. Otherwise only verified, unchanged content is deleted,
    never the mount point or excluded folders.
14. Given any runs, when `--status` runs, then each mapping's copy,
    verification, source-retention and last-check state is shown with migrated
    and remaining totals.
15. Given filenames with spaces, `&`, `()`, apostrophes, wildcards, Unicode,
    tabs or newlines, when they are migrated, verified and removed, then they
    are handled exactly.

## Dependencies and decisions

- [ADR 001: Safety model for migrating storage to raid-pc](../../adr/001-raidMigrationSafety.md)
- The raid-pc storage layout and SnapRAID parity are prerequisites for real
  migration, not for this implementation.

## Verification

- `linuxBootstrap/tests/migrateToRaidTests.sh` covers every acceptance
  criterion, using SSH, mount and free-space doubles plus real rsync in
  temporary directories. It is also run by `linuxBootstrap/tests/runTests.sh`.
- Review the preview against real mounts with real mappings before the first
  confirmed run.

## Change history

- 2026-10-18: created from the storage migration brief; refined with the
  repository CLI convention (`--confirm`, `--yes-delete`), explicit collision
  classification, mount identity, parity-gated SAFE TO REMOVE, shared
  unnumbered raid-pc folders and folder sources within a disk.
- 2026-10-18: moved from `linuxBootstrap/project/` (LB-001) to the repository
  `project/` for OMP 0.9; it is a linuxMigration requirement implemented in
  linuxBootstrap.
