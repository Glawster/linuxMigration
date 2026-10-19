# Migrating andy-pc storage to raid-pc

`migrateToRaid` moves media and file storage from the disks in `andy-pc` to its
long-term home, one mapping at a time, without risking the only copy of the
data. It is run on `andy-pc`, and on `raid-pc` for a disk attached there
(see [Running on raid-pc](#running-on-raid-pc)).

There are two kinds of destination:

| Destination | Holds | Reached by |
| --- | --- | --- |
| **raid-pc** storage pool (mergerFS + SnapRAID) | bulk Movies, TV and archive media | rsync over SSH |
| **`/mnt/media`** on andy-pc (internal 4 TB disk) | personal Pictures and personal/home Video, kept local permanently | local rsync |
| raid-pc storage pool, when run **on raid-pc** | content of disks attached to raid-pc by USB | local rsync |

```text
andy-pc sources                         destination
---------------                         -----------
/mnt/movie1, /mnt/movie2          ->    raid-pc  <pool>/Movies
/mnt/myPictures/Movies            ->    raid-pc  <pool>/Movies
/mnt/video2, /mnt/video3          ->    raid-pc  <pool>/TV
/mnt/myVideo/TV                   ->    raid-pc  <pool>/TV
/mnt/myPictures (rest)            ->    andy-pc  /mnt/media/Pictures
/mnt/myVideo (rest, not encrypted) ->   andy-pc  /mnt/media/Video
/mnt/myVideo/encrypted                  not migrated (handled separately)

raid-pc sources (run on raid-pc)        destination
--------------------------------        -----------
/mnt/oldVideo1/TV (old 2 TB disk, USB) -> raid-pc  /mnt/storage/TV
```

Once their content is verified in the right destinations, the USB `myPictures`
and `myVideo` disks can be retired. `/mnt/video1` does not survive the
migration: the old 2 TB disk is replaced by the internal `/mnt/media` disk.

`migrateToRaid` never provisions disks or filesystems. raid-pc storage and the
`/mnt/media` filesystem are created and mounted separately; the tool only
checks that the expected filesystem is mounted before it copies anything.

It never moves data. Every mapping goes through:

```text
COPY  ->  VERIFY  ->  RECORD  ->  (separately, on request)  REMOVE SOURCE
```

Source data is never deleted by a migration run. Deletion is a separate
command that refuses to run unless the disk has been proven safe to remove.

Requirement: [001 raid-pc storage migration](../../project/requirements/features/001-raidMigration.md).
Safety decisions: [ADR 001](../../project/adr/001-raidMigrationSafety.md),
[ADR 002](../../project/adr/002-localMigrationDestination.md),
[ADR 003](../../project/adr/003-migrateOnRaidPc.md).

## Contents

- [Configuration](#configuration)
- [Local destination](#local-destination)
- [Initial setup](#initial-setup)
- [Preview (the default)](#preview-the-default)
- [Migrating](#migrating)
- [Verification](#verification)
- [Resume behaviour](#resume-behaviour)
- [Files already on raid-pc](#files-already-on-raid-pc)
- [Checking status](#checking-status)
- [Is a disk safe to remove?](#is-a-disk-safe-to-remove)
- [Removing migrated source data](#removing-migrated-source-data)
- [State and logs](#state-and-logs)
- [Worked example](#worked-example)
- [Running on raid-pc](#running-on-raid-pc)

## Configuration

Mappings live in a JSON file, separate from the code:

```text
~/.config/migrateToRaid/config.json
```

Start from the reviewed template in this repository,
[`configs/migrateToRaid/config.json`](../configs/migrateToRaid/config.json).
`--config FILE` uses another file.

| Key | Meaning |
| --- | --- |
| `remoteHost`, `remoteUser` | SSH target for raid-pc (`remoteUser` may be empty to use `~/.ssh/config`). |
| `destinationMount` | The raid-pc storage pool mount point (for example the mergerFS namespace). Every destination must be inside it. |
| `destinationFsType` | Optional. Expected filesystem type of `destinationMount`, for example `fuse.mergerfs`. |
| `minFreeBytesAfter` | Free space that must remain after a copy (default 10 GiB). |
| `checksum` | `sha256sum` (default), `b2sum` or `md5sum`, used for full verification. |
| `excludes` | Top-level names never migrated (default `lost+found`, `$RECYCLE.BIN`, `System Volume Information`). |
| `protection` | The raid-pc parity/protection readiness check (see [below](#parity-protection)). |
| `localDestination` | Optional. The local destination on the machine running the tool (see [Local destination](#local-destination)). |
| `mappings` | The list of sources to migrate. |

Each mapping:

| Key | Meaning |
| --- | --- |
| `name` | Short identifier used on the command line (`movie1`). |
| `label` | Readable name (`Movies 1`). |
| `type` | Category used by `--type`: `movies`, `tv`, `video`, `music`, `pictures`, `files`. |
| `source` | Folder on andy-pc. Normally a whole mounted disk. |
| `mountPoint` | Optional. The mounted disk containing `source`, when `source` is a folder inside it. Defaults to `source`. |
| `excludes` | Optional. Top-level folders of this source that another mapping handles, or that are deliberately not migrated. |
| `target` | `remote` (default) for raid-pc, or `local` for `localDestination`. |
| `destination` | Absolute path inside `destinationMount` on raid-pc, or inside `localDestination.mount` for a `local` mapping. |
| `uuid` | Optional. The filesystem UUID expected at `mountPoint`. A placeholder is refused. |
| `enabled` | `true` to include the mapping in `--all` and `--type`. |

Several mappings may share one destination. The template merges `movie1`,
`movie2` and `/mnt/myPictures/Movies` into `Movies`, and `video2`, `video3`
and `/mnt/myVideo/TV` into `TV`. On raid-pc, the old `video1` disk's `TV`
folder joins the same pool `TV` folder.
Each mapping compares only its own source against the shared folder, so files
from other disks are ignored. If two disks hold the same path with different
content, the second disk reports a [conflict](#files-already-on-raid-pc) and
nothing is overwritten.

A folder inside a disk is migrated with `mountPoint`, as `myVideoTV` does for
`/mnt/myVideo/TV`. A mapping whose source contains another mapping's source must
exclude that folder (`"excludes": ["TV"]` on `myVideo`). Overlapping mappings
are rejected when the configuration is loaded. The folders of one disk may go
to different destinations: `/mnt/myPictures/Movies` goes to raid-pc while the
rest of `/mnt/myPictures` stays on `/mnt/media`.

`myVideo` also excludes `encrypted`. That folder is handled separately and is
never copied to raid-pc or `/mnt/media` by this tool. Because no mapping covers
it, `--check` keeps reporting the `myVideo` disk as NOT SAFE TO REMOVE DISK
while `encrypted` is still on it.

The template ships with **every mapping disabled** and placeholders such as
`<RAID_STORAGE_MOUNT>/Movies` and `<MEDIA_FS_UUID>`. A placeholder is refused
before any network or data operation, so nothing can be migrated until the
raid-pc layout and the `/mnt/media` filesystem identity have been written in.

## Local destination

Mappings with `"target": "local"` copy to a disk mounted on the machine running
the tool instead of over SSH: `/mnt/media` on andy-pc, or the storage pool when
the tool runs [on raid-pc](#running-on-raid-pc). The same safety model applies: preview by default, missing entries
only, conflicts never overwritten, resumable rsync with a partial directory,
quick or full verification, source stability checks, and source removal only
after `--check` reports SAFE.

```json
"localDestination": {
  "mount": "/mnt/media",
  "fsType": "ext4",
  "uuid": "<MEDIA_FS_UUID>",
  "protection": {
    "required": false
  }
}
```

| Key | Meaning |
| --- | --- |
| `mount` | Mount point of the local destination disk. Every `local` destination must be inside it. |
| `fsType` | Optional. Expected filesystem type, for example `ext4`. |
| `uuid` | Filesystem UUID of the disk that must be mounted at `mount` (`findmnt -no UUID /mnt/media`). |
| `source` | Expected mount source (`findmnt -no SOURCE /mnt/storage`), for a filesystem without a UUID such as a mergerFS pool. At least one of `uuid` and `source` is required. |
| `protection` | `{"required": false}` to accept single-copy storage, or a `name`, `command` and `successExitCodes` check run on andy-pc (see below). |

Before every copy and every `--check`, the local destination must be
**positively identified**:

- a filesystem is genuinely mounted at `mount`. An empty `/mnt/media`
  directory on the operating-system disk is refused, so a missing disk can
  never silently fill the root filesystem;
- the mounted filesystem has the configured `uuid` or `source` (and `fsType`,
  if set), so a different disk mounted at `/mnt/media` is refused;
- the destination folder resolves to that filesystem, not to another mount
  inside it or outside it;
- it is not the source's own filesystem, and the destination does not overlap
  its source path.

No SSH connection is made for a local mapping.

### Local protection

SAFE TO REMOVE depends on the protection of each mapping's own destination:

```text
raid-pc:     full verification + SnapRAID protection           -> SAFE TO REMOVE source
/mnt/media:  full verification + accepted single-copy storage  -> SAFE TO REMOVE source
```

`/mnt/media` is the new **authoritative internal copy** of Pictures and
personal Video. No parity or backup layer has been designed for it, so the
configuration accepts it explicitly as single-copy storage:

```json
"protection": { "required": false }
```

This **does not mean `/mnt/media` is backed up or redundant.** It records the
decision that the new internal disk replaces the USB `myPictures` and
`myVideo` disks as the one authoritative copy, so that once a full checksum
verification has passed, those USB disks can be retired.

`--check` never prints a bare SAFE: the line before it states the basis, so
the two cases cannot be confused later:

```text
raid-pc mapping                      /mnt/media mapping
---------------                      ------------------
COPY VERIFIED                        COPY VERIFIED
SNAPRAID PARITY VERIFIED             DESTINATION ACCEPTED AS AUTHORITATIVE (single copy, not redundant)
SAFE TO REMOVE DISK                  SAFE TO REMOVE SOURCE FOLDER
```

The verified-protection line is the configured protection `name` in capitals
(`SnapRAID parity` gives `SNAPRAID PARITY VERIFIED`). A disk verdict lists the
basis of each of its mappings, and `--status` shows `safe(1 copy)` rather than
`safe` for single-copy storage.

If a backup of `/mnt/media` is added later, replace `required: false` with a
check that succeeds only when the backup is current:

```json
"protection": {
  "name": "media backup",
  "command": "<command that succeeds when /mnt/media is backed up>",
  "successExitCodes": [0]
}
```

Without either setting, a local mapping is never SAFE. raid-pc protection
cannot be turned off.

## Initial setup

1. Install the local prerequisites on andy-pc: `rsync`, `jq`, `findmnt`
   (util-linux), coreutils and the `organiseMyProjects` Python package (for
   `logUtils.sh`).
2. Ensure raid-pc has `rsync` and the configured checksum tool.
3. Mount the `/mnt/media` disk persistently (by UUID in `/etc/fstab`). Its
   filesystem is created outside this tool.
4. Copy the template and replace the placeholders:

   ```bash
   mkdir -p ~/.config/migrateToRaid
   cp ~/bin/linuxBootstrap/configs/migrateToRaid/config.json ~/.config/migrateToRaid/
   ```

5. Enable mappings one at a time as their destinations are confirmed. Local
   mappings do not depend on raid-pc and can be migrated first.

### SSH requirements

All raid-pc access uses SSH in batch mode (no prompts):

- `andy@raid-pc` (or the configured target) must accept key-based login from
  andy-pc. Test with `ssh -o BatchMode=yes raid-pc true`.
- `raid-pc` must resolve from andy-pc (DNS, `/etc/hosts` or an `~/.ssh/config`
  `Host` entry).
- The remote login shell must be `bash`.
- The remote user must be able to write to the destination folders.

## Preview (the default)

Without `--confirm` nothing is copied, created, deleted or recorded:

```bash
migrateToRaid --source movie1
migrateToRaid --type movies
migrateToRaid --all
```

The preview checks everything a real run checks and prints the source, the
destination, the mounted filesystem, whether raid-pc is reachable (or, for a
local mapping, the verified `/mnt/media` mount), the source size, the space
available at the destination, how many entries are already identical there,
what would be copied and any conflicts. It also shows the exact `rsync`
command that would run.

Following the repository convention, there is no `--dry-run` flag: preview is
the default and `-y`/`--confirm` performs the work.

## Migrating

```bash
migrateToRaid --source movie1 --confirm
migrateToRaid --source movie1 --confirm --verify full
```

Before copying anything, each mapping must pass these checks, or it is
abandoned and nothing changes:

- the disk is **genuinely mounted** at its mount point (`findmnt`). An empty
  mount-point directory is never treated as the source;
- the mounted filesystem has a UUID, matches `uuid` if configured, and matches
  the UUID recorded when this mapping was first migrated;
- the source is readable, and the whole tree can be listed (an unreadable
  folder aborts the mapping instead of silently being skipped);
- raid-pc answers over SSH and has `rsync` and the checksum tool;
- the raid-pc storage pool is mounted at `destinationMount` (and is of
  `destinationFsType`), and the destination is inside it, so an unmounted pool
  can never fill the operating-system disk;
- for a local mapping instead: the [local destination](#local-destination) is
  mounted with its configured UUID, and is not the source filesystem;
- the destination exists or can be created, and is writable;
- the free space covers the data still to copy plus `minFreeBytesAfter`.

The copy uses rsync, over SSH for raid-pc and directly for a local mapping:

```text
rsync --from0 --files-from=<missing entries> --dirs --links --times
      --ignore-existing --partial-dir=.rsync-partial --protect-args
      --timeout=300 --info=progress2 --stats --log-file=...
      (NTFS/FAT sources: --chmod=D755,F644; others: --perms --hard-links)
```

- Only entries classified as **missing** on raid-pc are given to rsync.
- `--ignore-existing` is a second guard: rsync can never replace a file that
  already exists on raid-pc.
- There is no `--delete` and no `--remove-source-files`.
- Timestamps and directory structure are preserved. Owners are not, because
  the remote user is not root. NTFS permission bits mean nothing, so files
  from NTFS or FAT get ordinary `755`/`644` permissions.
- `--timeout` makes a dead network fail the run instead of hanging it.

After each copy pass, both sides are listed again (the final synchronisation
pass). If new files appeared on the source while it was being copied, another
pass copies them, up to three passes.

## Verification

Verification is a separate pass after the copy, and a migration is not complete
until it succeeds.

- `--verify quick` (the default) compares every entry's relative path, type,
  size and modification time on both machines.
- `--verify full` also computes checksums of every file on andy-pc and on
  raid-pc at the same time, then compares them. A progress bar shows both
  sides.

Both levels end with a stability check: the source is listed again and must be
exactly the same as when verification started. If anything changed during the
run, verification fails and the run must be repeated.

To verify an already-copied mapping again, for example at the full level, run:

```bash
migrateToRaid --source movie1 --verify-only --verify full
```

Quick verification never makes a disk safe to remove.

## Resume behaviour

Runs can be interrupted (Ctrl-C, network loss, reboot) and simply re-run:

- rsync writes each file to a temporary name and renames it only when it is
  complete, so a destination path never holds a partial file.
- Partial data from an interrupted file is kept in a `.rsync-partial` folder
  next to it and reused on the next run. The final path stays absent, so the
  next run classifies the file as *missing* (not as a conflict) and resumes it.
- `.rsync-partial` folders are ignored when the destination is listed.
- Files that already arrived are classified as identical and are not sent again.
- An interrupted copy is recorded as `partial` and its verification as
  `pending`. It is never recorded as complete.

If rsync is killed outright (`kill -9`, power loss), it can leave a hidden
`.<name>.XXXXXX` temporary file on raid-pc. It is never mistaken for the real
file and can be deleted by hand.

## Files already on raid-pc

Before copying, every source entry is classified against raid-pc:

| Destination | Result |
| --- | --- |
| missing | copied |
| exists and identical (same type, size, modification time) | skipped |
| exists and different | **conflict**: never overwritten |

Conflicts are written to `~/.local/state/migrateToRaid/<name>.conflicts` with
both sides' size and timestamp. The mapping is recorded as `conflicts` and
cannot be verified until they are resolved: rename or remove the destination
file on raid-pc, or the source file, and run again.

Full verification checks the content of the files classified as identical.

## Checking status

```bash
migrateToRaid --status
```

```text
Source           Type      Copy         Verify         Source    Last check           Size
------------------------------------------------------------------------------------------
movie1           movies    complete     verified(full) retained  safe               3.2TiB
movie2           movies    partial      pending        retained  -                  3.6TiB
myPictures       pictures  not run      -              retained  -                       ?

Migrated:  3.2TiB verified
Remaining: 7.1TiB used on unverified sources
```

A copy status of `interrupted` means a run stopped without recording its
outcome. Re-run it. The size of a mapping that covers only part of a disk is
shown once it has been verified. `Local protection:` appears once a local
mapping has been checked.

## Is a disk safe to remove?

```bash
migrateToRaid --check movie1
migrateToRaid --check          # every mapping
```

The answer distinguishes two conditions.

**COPY VERIFIED** means all of the following were confirmed now, not just read
from records:

- the disk mounted now is the one that was migrated (same UUID and mount
  point), so a different disk mounted at `/mnt/movie1` can never inherit the
  old disk's state;
- the copy completed, with no unresolved conflicts;
- a **full** checksum verification succeeded;
- the source has not changed since it was verified (it is listed again and
  compared with the stored manifest);
- the destination is reachable (for a local mapping: mounted with its
  configured UUID) and still matches the verified manifest.

**SAFE TO REMOVE DISK** additionally requires the protection check of the
mapping's destination to pass: [raid-pc parity](#parity-protection), or
[local protection](#local-protection). Anything else prints
**NOT SAFE TO REMOVE DISK** with the reasons.

A mapping that covers only part of a disk (a `mountPoint` folder, or a mapping
with `excludes`) reports **SAFE TO REMOVE SOURCE FOLDER**. A **Disk** verdict
follows it, and that disk is safe only when every mapping on it is safe and
every top-level item on the disk belongs to one of those mappings. Anything
left over is listed. A disk split between raid-pc and `/mnt/media`, such as
`/mnt/myPictures`, is safe only when both parts are.

`--check` exits with status 0 only when every verdict is safe.

### Parity protection

raid-pc has four data disks and one SnapRAID parity disk (see
[raid-pc](raidPc.md)). SnapRAID parity is a snapshot: until a sync has covered
the migrated data, losing a raid-pc disk would lose data that no longer has a
copy on andy-pc. So a copy can be **COPY VERIFIED** and still
**NOT SAFE TO REMOVE DISK**.

The check is configuration, not code, and does not assume any number of disks:

```json
"protection": {
  "name": "SnapRAID parity",
  "command": "sudo -n snapraid diff",
  "successExitCodes": [0]
}
```

The command runs on raid-pc over SSH every time `--check` or `--remove-source`
runs. Its exit code must be in `successExitCodes`. Choose a command that
succeeds only when parity covers the current data. For example, `snapraid diff`
reports whether a sync is needed, but check its exit codes for the installed
SnapRAID version. `sudo -n` needs a matching sudoers rule. While the command is
still the template placeholder, every disk is NOT SAFE TO REMOVE.

## Removing migrated source data

```bash
migrateToRaid --source movie1 --remove-source              # preview the plan
migrateToRaid --source movie1 --remove-source --confirm    # asks you to type "movie1"
```

Removal:

- needs exactly one `--source`;
- runs the full [safety check](#is-a-disk-safe-to-remove) first and refuses
  unless it is SAFE (so copy, full verification, current source, reachable
  destination and protection are all re-confirmed);
- shows what will happen, then asks you to type the mapping name. When there
  is no terminal it refuses, unless `--yes-delete` is given (`-y` only means
  `--confirm` and never skips this);
- deletes only the files and links in the verified manifest, and only if each
  one still has its verified size and modification time;
- then removes directories that became empty, deepest first;
- never deletes the mount point, the mapping's source folder, excluded
  folders, or anything that changed or appeared after verification;
- writes every deletion to `<name>-<timestamp>.removed`.

## State and logs

Everything lives in one folder:

```text
~/.local/state/migrateToRaid/
├── migrateToRaid-<date>.log         daily log (logUtils)
├── migrateToRaid.lock               prevents two runs at once
├── protection.state                 last raid-pc protection check
├── protection-local.state           last local destination protection check
├── <name>.state                     current state of each mapping
├── <name>.history                   timestamped audit trail
├── <name>.manifest                  verified source manifest
├── <name>.conflicts                 destination conflicts to review
├── <name>-<timestamp>.rsync.log     every file rsync transferred
└── <name>-<timestamp>.removed       every file deleted from the source
```

`<name>.state` records the source and destination (and whether it is local),
source filesystem UUID,
mount point and type, copy start, completion and result, files and bytes
copied, verification level, result and time, the verified fingerprint and
size, conflicts, source removal and the last error.

To start a mapping again from scratch, for example after deliberately
reformatting and reusing a disk, move its `<name>.*` files out of the state
folder.

## Worked example

These paths are placeholders until the raid-pc layout is confirmed.

```bash
# 1. Decide the destination and enable the mapping in
#    ~/.config/migrateToRaid/config.json:
#    "destinationMount": "/raidStoragePoint"
#    { "name": "movie1", ..., "destination": "/raidStoragePoint/Movies", "enabled": true }

# 2. Preview: checks, sizes, conflicts, rsync command; nothing changes
migrateToRaid --source movie1

# 3. Copy and fully verify (re-run the same command after any interruption)
migrateToRaid --source movie1 --confirm --verify full

# 4. Review progress across all disks
migrateToRaid --status

# 5. Ask whether the disk can go; expect NOT SAFE until raid-pc parity is synced
migrateToRaid --check movie1

# 6. Once SAFE TO REMOVE DISK: preview, then remove the migrated content
migrateToRaid --source movie1 --remove-source
migrateToRaid --source movie1 --remove-source --confirm
```

### Live sources

`/mnt/video2` is exported over NFS to tv-pc, where qBittorrent writes
downloads. A source that is still being written to will keep failing the
stability check or `--check`. Pause those writers, or migrate that disk last,
before expecting it to become SAFE TO REMOVE.

## Running on raid-pc

The internal 2 TB disk at `/mnt/video1` on andy-pc is replaced by the 4 TB
SkyHawk, which becomes `/mnt/media`. The old disk holds only TV, so its `TV`
folder goes to the raid-pc pool. Rather than copy it twice over the network,
the disk is attached to raid-pc by USB and `migrateToRaid` runs **on raid-pc**,
where the pool is the local destination. It is the same tool and the same
safety model; only the configuration differs.

```text
raid-pc
-------
/mnt/oldVideo1/TV  (old 2 TB NTFS disk, USB)  ->  /mnt/storage/TV  (mergerFS pool)
```

The raid-pc template is
[`configs/migrateToRaid/raidPcConfig.json`](../configs/migrateToRaid/raidPcConfig.json):

- `localDestination.mount` is `/mnt/storage`, of type `fuse.mergerfs`. A
  mergerFS pool has no filesystem UUID, so it is identified by its mount
  `source` instead; read it with `findmnt -no SOURCE /mnt/storage` once the
  pool exists.
- `localDestination.protection` is the SnapRAID check, run locally on raid-pc.
  Unlike `/mnt/media`, the pool is not accepted as single-copy storage: the
  old disk becomes SAFE only when parity covers the copy.
- The `video1` mapping copies `/mnt/oldVideo1/TV` (with `mountPoint`
  `/mnt/oldVideo1`) into `/mnt/storage/TV`, so the shows are not nested in
  `TV/TV`. Its `uuid` is the old disk's NTFS UUID, `9400247000245B8C`, so only
  that disk is accepted at the temporary mount.

The old disk also has a `.Trash-1000` folder. No mapping covers it, so `--check`
reports SAFE TO REMOVE SOURCE FOLDER for `TV` but NOT SAFE TO REMOVE DISK until
the trash is reviewed and emptied.

Prerequisites on raid-pc:

1. The storage pool is provisioned and mounted at `/mnt/storage` (outside this
   tool), and `/mnt/storage/TV` is writable by the user running the migration.
2. This branch of `~/bin` is checked out, and `jq`, `rsync`, `findmnt`, `flock`
   and the `organiseMyProjects` Python package (for `logUtils.sh`) are
   installed. `LOG_UTILS=/path/to/logUtils.sh` can point at a copy instead.
3. `sudo -n snapraid diff` (or the chosen protection command) works without a
   password prompt.

Then, on raid-pc:

```bash
mkdir -p ~/.config/migrateToRaid
cp ~/bin/linuxBootstrap/configs/migrateToRaid/raidPcConfig.json ~/.config/migrateToRaid/config.json
# set localDestination.source and protection.command, then "enabled": true

migrateToRaid --source video1                          # preview
migrateToRaid --source video1 --confirm --verify full  # copy and verify
sudo snapraid sync                                     # protect the copy
migrateToRaid --check video1
```

State and logs for this migration live on raid-pc, so `--status` on andy-pc
does not show it. The disk is mounted read-only, so `--remove-source` cannot
delete from it; once the check is SAFE, unmount it and retire it. On andy-pc,
`/mnt/video1` is not recreated.
