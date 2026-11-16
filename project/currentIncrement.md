# Current Development Increment

## Increment

002 localMediaRebalance: rebalance local movies and TV to raid-pc

## Status

Blocked
<!-- Options: Active, Idle, Blocked, InReview -->

## Requirement

[project/requirements/features/002-localMediaRebalance.md](requirements/features/002-localMediaRebalance.md)

## Objective

Move the oldest movies and ended TV shows, as whole folders, from `/mnt/movies`
and `/mnt/video` to raid-pc until each disk is at most 50% occupied, without
splitting a show between stores.

## Scope

Rebalance planning in `linuxBootstrap/lib/raidMigrationPlan.sh`, its hooks in
`lib/raidMigration.sh` and `lib/raidMigrationStore.sh`, the configuration
template, tests and the migrateToRaid guide
([ADR 005](adr/005-rebalancePlan.md)). Merged to `main` in #97.

## Verification

- [x] Automated tests for every acceptance criterion
      (`linuxBootstrap/tests/migrateToRaidTests.sh`)
- [x] Read-only preview of both plans against the real disks
- [x] Review and merge `feature/localMediaRebalance` (#97)
- [ ] Finish the requirement 001 raid-pc migrations
- [ ] Move `linuxBackup` off `/mnt/video` to a retired USB disk
- [ ] Manual acceptance: review the real plans, then the first confirmed,
      fully verified rebalance and removal

## Next

The real rebalance is blocked until two things are done:

- **Requirement 001 migrations.** `myVideo`, `myVideoTV` and `myPictures` are
  complete. `movie2` is being copied from andy-pc, with `video3` queued after it.
  A shutdown interrupted the `myPicturesMovies` full verification. It has to be
  run again, with its disk mounted, before the source can be removed.
- **`linuxBackup` leaving `/mnt/video`.** It is still there.

Once both are done, preview both rebalance plans again against the real disks,
because raid-pc free space will have changed.
