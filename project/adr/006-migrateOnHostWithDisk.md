# 006: Migrating a disk on the machine it is attached to

- Status: Accepted
- Date: 2026-10-24
- Requirement: [001 raid-pc storage migration](../requirements/features/001-raidMigration.md)
- Related: [ADR 001](001-raidMigrationSafety.md), [ADR 002](002-localMigrationDestination.md), [ADR 003](003-migrateOnRaidPc.md)
- Supersedes: [ADR 004](004-migrateOnlyOnAndyPc.md)

## Context

ADR 004 restricted `migrateToRaid` to andy-pc, reaching raid-pc only over SSH.
In practice the USB source disks run at USB 2 speed on andy-pc, and every
andy-pc migration shares one gigabit link to raid-pc. On 2026-10-24 the
`movie2` USB disk was moved to raid-pc, where a copy into the pool is local and
leaves the network and andy-pc free for other migrations.

`migrateToRaid` reads its sources on the machine where it runs. Its
configuration describes raid-pc destinations as raid-pc sees them
(`/mnt/storage/...`), so the same mappings are valid on raid-pc; only the way
the pool is reached differs.

## Decisions

1. **Run on the machine the disk is attached to.** A source disk attached to
   raid-pc is migrated by running `migrateToRaid` on raid-pc. No remote-source
   transport is added: every source check, scan, checksum and removal runs
   where the source is mounted, so the ADR 001 safety model applies unchanged.
2. **One configuration for both machines.** raid-pc uses the same
   `~/.config/migrateToRaid/config.json` as andy-pc; nothing is removed or
   rewritten per host. When the short hostname is `remoteHost`, the tool is
   running on raid-pc, and raid-pc mappings reach the pool locally instead of
   over SSH: the same scripts run under local `bash`, rsync gets a local path,
   and no SSH connection is made.
3. **Same checks, same protection.** On raid-pc the pool must still be
   mounted at `destinationMount` with `destinationFsType`, and the destination
   must resolve inside it and not be the source's filesystem. The SnapRAID
   `protection` command runs locally. The pool is never accepted as
   single-copy storage, so SAFE TO REMOVE still needs parity in sync.
4. **Each disk is migrated where it is mounted.** A mapping whose disk is not
   attached to the machine running the tool is refused as not mounted, and a
   `/mnt/media` mapping runs only where `/mnt/media` is mounted (andy-pc).
   Each machine keeps its own state, manifests and logs.
5. **raid-pc prerequisites.** raid-pc runs `~/bin/migrateToRaid` from its own
   checkout of this repository, with `jq`, `rsync`, `flock` and `ntfs-3g`
   installed and `organiseMyProjects` importable from
   `~/Source/organiseMyProjects` (a user `.pth` file), and a copy of andy-pc's
   configuration. Mounting the source disk in raid-pc's `/etc/fstab` is done by
   hand with the same line as andy-pc's.

## Consequences

- `--status` and `--check` on each host show only that host's migrations; the
  `movie2` record on andy-pc from its interrupted 2026-10-22 run is stale and
  is not evidence for or against the copy made on raid-pc.
- Copies on raid-pc do not cross the network, but are still limited by the
  disk's USB port; a USB 2 port gives about 40 MB/s.
- raid-pc does not keep user services after logout (no lingering), so a long
  run is started from a terminal that stays open, or detached.
- The old video1 disk's hand copy, recorded by ADR 004, is unchanged; it is
  still not recorded or verified by `migrateToRaid`.
- Configuration changes are copied to raid-pc by hand; the two copies must
  be kept identical.
- Running on raid-pc is decided by hostname alone. A machine renamed to
  `remoteHost`'s name would treat its own disks as the pool, but the mount and
  filesystem-type checks still refuse anything that is not the mergerFS pool.
- ADR 004's mount-source identity for local destinations stays supported but
  unused.
