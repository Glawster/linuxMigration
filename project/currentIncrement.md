# Current Development Increment

## Increment

001 raidMigration: migrateToRaid implementation

## Status

InReview
<!-- Options: Active, Idle, Blocked, InReview -->

## Requirement

[project/requirements/features/001-raidMigration.md](requirements/features/001-raidMigration.md)

## Objective

Copy, verify and record the migration of andy-pc storage to raid-pc, or to the
local `/mnt/media` disk for personal pictures and video, with protection-gated,
explicit removal of source data.

## Scope

`linuxBootstrap/migrateToRaid.sh`, `linuxBootstrap/lib/raidMigration*.sh`, the
configuration template, tests and the migrateToRaid guide, on branch
`feature/migrateToRaid`.

## Verification

- [ ] Review and merge `feature/migrateToRaid`
- [x] Confirm the raid-pc storage layout and configure destinations
      (`/mnt/storage`)
- [ ] Configure the raid-pc protection check once SnapRAID parity is synced
- [ ] Mount the SkyHawk at `/mnt/media` and set `localDestination.uuid`
      (protection is accepted as single-copy, `"required": false`)
- [x] Attach the old video1 disk to raid-pc by USB at `/mnt/oldVideo1`
- [ ] Copy `/mnt/oldVideo1/TV` into `/mnt/storage/TV` by hand with rsync on
      raid-pc (outside `migrateToRaid`, ADR 004)
- [ ] Manual acceptance: preview real mappings, then the first confirmed,
      fully verified migration

## Next

Review the branch, then install `/mnt/media` so the local mappings can be
enabled ahead of the raid-pc layout.
