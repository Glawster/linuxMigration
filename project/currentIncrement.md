# Current Development Increment

## Increment

001 raidMigration: migrateToRaid implementation

## Status

InReview
<!-- Options: Active, Idle, Blocked, InReview -->

## Requirement

[project/requirements/features/001-raidMigration.md](requirements/features/001-raidMigration.md)

## Objective

Copy, verify and record the migration of andy-pc storage to raid-pc, with
parity-gated, explicit removal of source data.

## Scope

`linuxBootstrap/migrateToRaid.sh`, `linuxBootstrap/lib/raidMigration*.sh`, the
configuration template, tests and the migrateToRaid guide, on branch
`feature/migrateToRaid`.

## Verification

- [ ] Review and merge `feature/migrateToRaid`
- [ ] Confirm the raid-pc storage layout and configure destinations
- [ ] Configure the raid-pc protection check once SnapRAID parity is synced
- [ ] Manual acceptance: preview real mappings, then the first confirmed,
      fully verified migration

## Next

Review the branch, then confirm the raid-pc layout so mappings can be enabled.
