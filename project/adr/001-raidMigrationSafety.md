# 001: Safety model for migrating storage to raid-pc

- Status: Accepted
- Date: 2026-10-18
- Requirement: [001 raid-pc storage migration](../requirements/features/001-raidMigration.md)

## Context

`migrateToRaid` copies irreplaceable multi-terabyte media from andy-pc disks
to raid-pc so the disks can be removed. Transfers run for hours over the LAN,
sources can be written to while they run (for example `/mnt/video2` from
tv-pc), mount points can exist without their disk, several disks merge into
shared raid-pc folders, and raid-pc will initially run without SnapRAID
parity.

## Decisions

1. **Explicit classification instead of relying on rsync skipping.** Before
   each transfer, the source and destination are listed. Every source entry is
   classified as missing, identical (same type, size and mtime) or
   conflicting. Only missing entries are passed to rsync (`--files-from`).
   `--ignore-existing` stays on as a second guard. Conflicts are recorded,
   never overwritten.
2. **Dedicated partial directory.** `--partial-dir=.rsync-partial` keeps
   interrupted data away from final paths, so a resumed file is classified as
   missing rather than conflicting. Destination listings ignore these folders.
3. **Independent verification.** Quick verification compares fresh manifests.
   Full verification hashes every file on both machines with a coreutils
   checksum tool, independently of rsync. A final source listing must match
   the one taken before verification.
4. **Manifests do not prove safety forever.** The verified manifest and its
   fingerprint are stored, but `--check` always rescans the mounted source,
   compares its filesystem UUID and mount point with the recorded identity,
   and re-lists the destination.
5. **COPY VERIFIED is not SAFE TO REMOVE.** SAFE additionally requires a
   configurable protection command on raid-pc (for example a SnapRAID check
   that succeeds only when parity is in sync). It is a placeholder by default,
   so nothing is safe until parity exists. The tool makes no assumption about
   the number of disks.
6. **Disk-level coverage.** A mapping covering part of a disk reports only on
   its folder. A disk is safe only when every mapping on it is safe and every
   top-level entry belongs to a mapping. Overlapping mappings are rejected.
7. **Repository CLI convention.** Preview by default, `-y`/`--confirm` to act,
   no `--dry-run`. Deletion additionally needs a typed confirmation or
   `--yes-delete`, never `-y` alone.
8. **Bash with jq.** Implemented as a linuxBootstrap standalone script that
   reuses the repository's logUtils and test-double conventions.
   `remotePull.sh` is deliberately left unchanged to avoid regressions.

## Consequences

- Extra listing passes cost time on large trees, in exchange for explicit
  conflict reporting and auditability.
- Sources still being written to cannot become SAFE until their writers stop.
- Files that changed on the source after an earlier copy appear as conflicts
  and need manual resolution. They are never updated automatically.
- Full verification reads every byte on both machines. raid-pc may serve
  recently written files from page cache.
