# 003: Migrating disks attached to raid-pc

- Status: Superseded by [ADR 004](004-migrateOnlyOnAndyPc.md)
- Date: 2026-10-19
- Requirement: [001 raid-pc storage migration](../requirements/features/001-raidMigration.md)
- Related: [ADR 001](001-raidMigrationSafety.md), [ADR 002](002-localMigrationDestination.md)

## Context

The old 2 TB video1 disk holds only TV. It was to be copied to `/mnt/media` on
andy-pc from a temporary USB mount. Instead it is attached by USB to raid-pc at
`/mnt/oldVideo1`, and its `TV` folder belongs in the raid-pc pool's TV folder
(`/mnt/storage/TV`). `migrateToRaid` reads its sources on the machine where it
runs and reaches raid-pc only as a destination over SSH, so it could not copy
a disk mounted on raid-pc.

The raid-pc pool is mergerFS, which has no filesystem UUID, while ADR 002
required local destinations to be identified by UUID.

## Decisions

1. **Run the same tool on raid-pc.** A disk attached to raid-pc is migrated by
   running `migrateToRaid` on raid-pc with the pool as its local destination
   (`"target": "local"`, ADR 002). No remote-source transport is added: every
   source check, scan, checksum and removal already runs where the source is
   mounted, so the whole safety model applies unchanged.
2. **Separate configuration per host.** raid-pc uses its own
   `~/.config/migrateToRaid/config.json`, from the template
   `configs/migrateToRaid/raidPcConfig.json`. The andy-pc template no longer
   has a `video1` mapping.
3. **Identity by mount source when there is no UUID.** `localDestination`
   accepts `source`, the expected `findmnt` mount source, as an alternative
   to `uuid`. At least one is required, placeholders are refused, and a
   destination mounted from the source's own device is refused. Together with
   `fsType: fuse.mergerfs` and the genuine-mount check, this keeps an unmounted
   pool from ever filling the operating-system disk.
4. **The pool keeps SnapRAID protection.** On raid-pc the local destination's
   protection is the SnapRAID check, run locally. The pool is not accepted as
   single-copy storage, so SAFE TO REMOVE still needs parity.

## Consequences

- The video1 migration's state and logs live on raid-pc; `--status` on andy-pc
  does not show it.
- `~/bin` on raid-pc must carry this branch, with `jq`, `rsync`, `flock` and
  `organiseMyProjects` (or `LOG_UTILS`) installed.
- Nothing can be copied until the raid-pc pool is provisioned and its mount
  source is written into the configuration.
- A `source` identity is weaker than a UUID for a single disk; `uuid` remains
  the expected identity for ordinary filesystems such as `/mnt/media`.
