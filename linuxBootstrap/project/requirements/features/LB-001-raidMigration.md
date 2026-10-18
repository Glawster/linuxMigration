# LB-001 raidMigration

- Identifier: LB-001
- Status: In Progress
- Created: 2026-10-18
- Documentation: [documentation/raidMigration/](../../../documentation/raidMigration/migrateToRaid.md)
- Decisions: [ADR-001](../../adr/ADR-001-raidMigrationSafety.md)

## Purpose

Move media and file storage from the disks in `andy-pc` to the `raid-pc`
storage pool so that old disks can be removed or reused, without risking
irreplaceable multi-terabyte data.

Priorities, in order: safety, auditability, resumability, speed, convenience.

## Scope

Sources on andy-pc: `/mnt/movie1`, `/mnt/movie2`, `/mnt/video1`–`/mnt/video3`,
`/mnt/myVideo`, `/mnt/music`, `/mnt/myPictures`. Further mounts (`/mnt/home`,
`/mnt/games1`, `/mnt/games2`) may be added as mappings later.

raid-pc layout: one storage pool without per-disk numbering, for example
`<pool>/Movies` (movie1, movie2) and `<pool>/TV` (video1–video3 and
`/mnt/myVideo/TV`). The pool path and folder names stay configurable until the
layout is confirmed.

## Requirements

1. Workflow is COPY → VERIFY → RECORD; deleting the source is a separate,
   explicit operation. Never `mv` across machines.
2. Mappings are configuration, separate from code, individually enabled, with
   a name, label and type. Destination paths are not assumed.
3. rsync over SSH; preserve timestamps and structure; resumable; safe for any
   filename; no `--delete`; never silently overwrite a differing destination
   file; meaningful exit status.
4. Preview is the default; `-y`/`--confirm` performs the work (repository CLI
   convention; no `--dry-run` flag).
5. Selection by `--all`, `--source NAME` and `--type TYPE`.
6. Pre-flight checks: source exists, is genuinely mounted (`findmnt`) and
   readable; raid-pc reachable over SSH; destination inside a mounted pool,
   creatable and writable; enough free space; rsync available on both ends.
7. Verification is a separate pass: `--verify quick` (path, size, mtime) and
   `--verify full` (checksums on both machines), with visible progress.
8. Persistent per-mapping state and an audit log under
   `~/.local/state/migrateToRaid/`.
9. Destination collisions are classified before transfer as missing, identical
   or conflicting; conflicts are recorded and never overwritten.
10. Interrupted transfers never leave a partial file at a destination path and
    resume on the next run.
11. Source changes during migration are detected; a final synchronisation and
    stability check precede any verified result.
12. The source filesystem identity (UUID and mount point) is recorded and must
    match on every later run.
13. `--check` gives an unambiguous SAFE / NOT SAFE TO REMOVE DISK answer with
    reasons, distinguishing COPY VERIFIED from SAFE TO REMOVE. SAFE requires a
    full checksum verification of the current, unchanged source and a passing,
    configurable raid-pc parity/protection check.
14. `--remove-source` deletes only verified content, never the mount point,
    and only after the check passes and an explicit confirmation
    (`--yes-delete` for non-interactive use).
15. `--status` summarises every mapping and migrated/remaining totals.
16. Automated tests mock SSH, mounts and free space; no real data is touched.

## Acceptance

- [x] `migrateToRaid` implemented in `linuxBootstrap/` with a `~/bin` launcher
- [x] Template configuration with every mapping disabled and placeholder paths
- [x] Shared destinations and folder sources within a disk
- [x] Automated tests for every behaviour above (`tests/migrateToRaidTests.sh`)
- [x] User documentation with a worked example
- [ ] raid-pc storage layout confirmed and destinations configured
- [ ] Parity protection check configured once SnapRAID parity is synced
- [ ] First real migration previewed, copied and fully verified
