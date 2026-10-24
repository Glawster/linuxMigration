# 004: migrateToRaid runs only on andy-pc

- Status: Superseded by [ADR 006](006-migrateOnHostWithDisk.md)
- Date: 2026-10-19
- Requirement: [001 raid-pc storage migration](../requirements/features/001-raidMigration.md)
- Related: [ADR 001](001-raidMigrationSafety.md), [ADR 002](002-localMigrationDestination.md)
- Supersedes: [ADR 003](003-migrateOnRaidPc.md)

## Context

ADR 003 planned to migrate the old 2 TB video1 disk, attached by USB to raid-pc
at `/mnt/oldVideo1`, by running `migrateToRaid` on raid-pc. That disk is
instead being copied into `/mnt/storage/TV` by hand with rsync on raid-pc. No
other disk is expected to be attached to raid-pc for migration.

## Decisions

1. **andy-pc only.** `migrateToRaid` runs only on andy-pc. raid-pc is reached
   only as a destination over SSH; `/mnt/media` is the only local destination.
2. **No raid-pc configuration.** The `configs/migrateToRaid/raidPcConfig.json`
   template and the guide's "Running on raid-pc" section are removed.
3. **Mount-source identity stays.** `localDestination.source`, added by ADR 003
   for a filesystem without a UUID, remains supported and tested, but the
   template does not use it.

## Consequences

- The old video1 disk's copy is not recorded, verified or protection-gated by
  `migrateToRaid`; checking it before the disk is retired is a manual step.
- `~/bin` on raid-pc does not need this branch or its dependencies.
