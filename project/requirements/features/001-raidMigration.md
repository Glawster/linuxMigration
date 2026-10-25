# 001: raid-pc storage migration

## Status

InProgress

## Outcome

As the owner of andy-pc, I need to migrate my bulk media to the raid-pc
storage pool, and my personal pictures and video to a permanent internal disk
on andy-pc (`/mnt/media`), one source at a time, with independently verified
copies and an unambiguous answer on whether each old disk can be removed. This
lets disks be retired without risking irreplaceable multi-terabyte data.

Priorities, in order: safety, auditability, resumability, speed, convenience.

## Context

- andy-pc holds media on several mostly 4 TB NTFS disks, several nearly full:
  `/mnt/movie1`, `/mnt/movie2`, `/mnt/video1`–`/mnt/video3`, `/mnt/myVideo`,
  `/mnt/music`, `/mnt/myPictures` (and `/mnt/home`, `/mnt/games1`,
  `/mnt/games2`).
- raid-pc is the bulk Movies/TV/archive store: a mergerFS pool over four 4 TB
  SMR data disks with SnapRAID parity on a fifth (a CMR Seagate IronWolf
  `ST4000VN006`). All five passed extended SMART self-tests. Parity is a
  snapshot, so migrated data is protected only after a sync.
- The raid-pc pool is mounted at `/mnt/storage` on raid-pc (NFS-mounted at
  `/mnt/raid` on andy-pc) and has no per-disk numbering: sources merge into
  shared folders, `/mnt/storage/Movies` (`/mnt/movie2/Movies`,
  `/mnt/myPictures/Movies`) and `/mnt/storage/TV` (`/mnt/video3/TV`,
  `/mnt/myVideo/TV`).
- `/mnt/movie1` and `/mnt/video2` stay on andy-pc and are renamed to
  `/mnt/movies` and `/mnt/video`; they are not migrated.
- `/mnt/media` is a new internal 4 TB disk on andy-pc (Seagate SkyHawk
  `ST4000VX016`, serial `ZW635K7Z`, passed extended SMART). It is the permanent
  local home for personal Pictures (`/mnt/media/Pictures`, the rest of
  `/mnt/myPictures`) and personal/home Video (`/mnt/media/homeVideo`, the rest of
  `/mnt/myVideo`). It replaces the internal 2 TB `/mnt/video1` disk;
  `/mnt/video1` is not kept as a mount point.
- The old 2 TB video1 disk holds only TV. It is attached by USB to raid-pc at
  `/mnt/oldVideo1`, and its `TV` folder is copied into the raid-pc pool's TV
  folder (`/mnt/storage/TV`) by hand with rsync on raid-pc, outside this tool.
  The USB `myPictures` and `myVideo` disks and the `movie2` and `video3` disks
  are retired
  once their content is verified in the right destinations.
- `/mnt/myVideo/encrypted`, and `/mnt/myVideo/decrypted` where it is unlocked,
  are handled separately and are not migrated.
- Transfers run for many hours over the LAN and may be interrupted. Some sources
  are written to while in use (for example `/mnt/video2` by tv-pc).
- The tool is implemented in `linuxBootstrap/`
  ([guide](../../../linuxBootstrap/documentation/migrateToRaid.md)).

## Scope

- A Bash command, `migrateToRaid`, run on the machine the source disk is
  attached to: andy-pc, or raid-pc for a disk moved there, with one shared
  configuration (ADR 006).
- JSON configuration of mappings, separate from the implementation. Each
  mapping has a name, label and type, can be enabled individually, may share a
  destination with other mappings, and may migrate a folder inside a mounted
  disk.
- Destinations on raid-pc over SSH (the default) and on one local destination
  on andy-pc (`/mnt/media`), selected per mapping.
- A preview by default, and copying with rsync (over SSH for raid-pc) only
  with `--confirm`.
- Selection by `--all`, `--source NAME` and `--type TYPE`.
- Pre-flight checks, classification of destination collisions, resumable
  transfer, separate quick or full verification, final source-stability
  checks, persistent state and audit logs.
- `--status`, `--check` (COPY VERIFIED and SAFE / NOT SAFE TO REMOVE, per
  mapping and per disk) and explicit `--remove-source`.
- Automated tests and user documentation.

## Out of scope

- Deciding or provisioning the raid-pc storage layout, mergerFS or SnapRAID,
  or partitioning, formatting or mounting the `/mnt/media` disk.
- Migrating `/mnt/myVideo/encrypted` or `/mnt/myVideo/decrypted`.
- Deduplicating media or reorganising library folder structures.
- Two-way synchronisation, or updating destination files that differ from the
  source.
- Migrating ownership metadata (the remote user is not root).

## Acceptance criteria

1. Given the template configuration, when it is loaded, then every mapping is
   disabled, raid-pc destinations and the local destination UUID are
   placeholders, and placeholders are refused before any network or data
   operation.
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
   entries are recorded as conflicts and never overwritten, except metadata
   files (criterion 24).
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
    it reports COPY VERIFIED, and SAFE TO REMOVE only if the protection check
    of that mapping's destination also passes (the raid-pc check, or the local
    destination's check unless the owner has explicitly accepted it as
    single-copy storage with `"required": false`, as the template does for
    `/mnt/media`). Otherwise it reports NOT SAFE with reasons. Quick verification
    is never SAFE.
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
16. Given a mapping with a local destination, when it is previewed, migrated,
    verified, checked or removed, then criteria 2 and 5–15 apply unchanged and
    no SSH connection is made.
17. Given a local destination mount point with no filesystem mounted, a
    filesystem whose UUID or type differs from the configuration, a
    destination that resolves outside that filesystem, a destination on the
    source's own filesystem, or a destination overlapping its source path,
    when a migration or check runs, then it is refused and nothing is copied
    or recorded as verified.
18. Given one disk whose mappings go to raid-pc and to the local destination,
    when `--check` runs, then each mapping is judged against its own
    destination and the disk is SAFE only when all of them are.
19. Given the template configuration, then `/mnt/myPictures/Movies` maps to
    raid-pc Movies, the rest of `/mnt/myPictures` to `/mnt/media/Pictures`,
    `/mnt/myVideo/TV` to raid-pc TV, the rest of `/mnt/myVideo` except `TV`,
    `encrypted` and `decrypted` to `/mnt/media/homeVideo`, `/mnt/movie2/Movies` and
    `/mnt/video3/TV` to raid-pc `/mnt/storage/Movies` and `/mnt/storage/TV`,
    no mapping uses `/mnt/movie1`, `/mnt/video2`, `/mnt/video1` or the old
    video1 disk, and `/mnt/media` is accepted as single-copy storage.
20. Given a SAFE verdict, when `--check` or `--status` reports it, then its
    basis is stated: verified protection (for example
    `SNAPRAID PARITY VERIFIED`) or
    `DESTINATION ACCEPTED AS AUTHORITATIVE (single copy, not redundant)`, and
    `--status` shows single-copy SAFE as `safe(1 copy)`.
21. Withdrawn: there is no raid-pc template configuration (ADR 004).
22. Given a local destination without a filesystem UUID, when it is identified
    by its mount source, then a migration or check is refused if the source
    is missing or a placeholder, the mounted source differs, nothing is
    mounted, or it is the source's own device; otherwise criteria 16 and 17
    apply unchanged.

23. Given the shared configuration on raid-pc (its short hostname is
    `remoteHost`), when a raid-pc mapping is migrated, checked or removed,
    then the pool is reached locally with no SSH connection, the mount,
    filesystem-type and protection checks still apply, and on any other host
    raid-pc is still reached over SSH.

24. Given a differing destination file whose extension is in
    `metadataExtensions` (default `jpg`, `jpeg`, `png`, `xml`, `nfo`), when a
    migration runs, then it is replaced if the source copy is newer and kept
    if the destination copy is as new or newer, it is not a conflict, a kept
    file does not fail verification or `--check`, an older destination copy
    does fail `--check`, and video and other files still conflict.

25. Given any run, when it starts, then a header on screen and in the log
    names the repository version (ADR 008), the host, the action and mode,
    and the command line; `--version` prints the version;
    and a confirmed copy records the version and host in the mapping's state.
26. Given a source folder or file that other users cannot read, or a private
    folder already at the destination, when a copy runs, then every copied
    folder and file, and the existing folder, end readable by other users
    (`permissions`, default `Dgo+rx,Fgo+r`); an empty value keeps the source
    permissions, and an invalid value is refused before anything is copied.

## Dependencies and decisions

- [ADR 001: Safety model for migrating storage to raid-pc](../../adr/001-raidMigrationSafety.md)
- [ADR 002: Local destinations alongside raid-pc](../../adr/002-localMigrationDestination.md)
- [ADR 004: migrateToRaid runs only on andy-pc](../../adr/004-migrateOnlyOnAndyPc.md)
  (supersedes ADR 003; superseded by ADR 006)
- [ADR 006: Migrating a disk on the machine it is attached to](../../adr/006-migrateOnHostWithDisk.md)
- [ADR 007: Newer artwork and metadata replace older copies](../../adr/007-newerMetadataWins.md)
- The raid-pc storage layout and SnapRAID parity are prerequisites for real
  migration to raid-pc, and a mounted `/mnt/media` with its UUID configured is
  a prerequisite for local migration; neither is a prerequisite for this
  implementation.

## Verification

- `linuxBootstrap/tests/migrateToRaidTests.sh` covers every acceptance
  criterion, using SSH, mount and free-space doubles plus real rsync in
  temporary directories. It is also run by `linuxBootstrap/tests/runTests.sh`.
- Review the preview against real mounts with real mappings before the first
  confirmed run, including a local mapping with `/mnt/media` unmounted to
  confirm the refusal.

## Change history

- 2026-10-18: created from the storage migration brief; refined with the
  repository CLI convention (`--confirm`, `--yes-delete`), explicit collision
  classification, mount identity, parity-gated SAFE TO REMOVE, shared
  unnumbered raid-pc folders and folder sources within a disk.
- 2026-10-18: moved from `linuxBootstrap/project/` (LB-001) to the repository
  `project/` for OMP 0.9; it is a linuxMigration requirement implemented in
  linuxBootstrap.
- 2026-10-19: refined for the andy-pc local-media plan: a local destination
  (`/mnt/media`) alongside raid-pc, `myPictures` and `myVideo` split between
  raid-pc and `/mnt/media`, `encrypted` excluded, `/mnt/video1` replaced by
  `/mnt/media`, and the confirmed raid-pc disk roles (criteria 16–19).
- 2026-10-19: the old video1 disk moves to raid-pc by USB and its `TV` goes to
  the pool, migrated by running the tool on raid-pc; local destinations may be
  identified by mount source (criteria 21–22, ADR 003).
- 2026-10-19: `/mnt/media` accepted as the single authoritative copy
  (`"required": false`), and every SAFE verdict states its basis
  (criterion 20).
- 2026-10-19: the tool runs only on andy-pc; the old video1 disk is copied by
  hand on raid-pc (ADR 004, criterion 21 withdrawn). The pool is
  `/mnt/storage`; `/mnt/movie2/Movies` and `/mnt/video3/TV` migrate as folders,
  and `/mnt/movie1` and `/mnt/video2` stay local (criterion 19).
- 2026-10-19: the `myVideo` remainder goes to `/mnt/media/homeVideo`
  (criterion 19).
- 2026-10-19: the `movie2` and `video3` disks are retired once migrated, and
  `decrypted` is excluded from `myVideo` (criterion 19).
- 2026-10-24: a source disk attached to raid-pc is migrated by running the
  tool on raid-pc, with the same configuration as andy-pc and the pool reached
  locally (ADR 006, superseding ADR 004, criterion 23); `movie2` is the first.
- 2026-10-24: differing artwork and metadata files are resolved by age, the
  newer copy winning, instead of being conflicts (ADR 007, criteria 5 and 24).
- 2026-10-24: every run opens with a versioned header, and copies record the
  tool version and host (criterion 25).
- 2026-10-24: the header reports the repository version instead of a
  tool-specific one (ADR 008, criterion 25).
- 2026-10-25: copies are made readable by other users such as Plex, after 45
  private TV folders on raid-pc were invisible to Plex (criterion 26).
