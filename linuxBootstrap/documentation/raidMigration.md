# Migrating andy-pc storage to raid-pc

`migrateToRaid` moves media and file storage from the disks in `andy-pc` to the
`raid-pc` storage pool, one mapping at a time, without risking the only copy of
the data. It is run on `andy-pc`.

It never moves data. Every mapping goes through:

```text
COPY  ->  VERIFY  ->  RECORD  ->  (separately, on request)  REMOVE SOURCE
```

Source data is never deleted by a migration run. Deletion is a separate
command that refuses to run unless the disk has been proven safe to remove.

## Contents

- [Configuration](#configuration)
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
| `mappings` | The list of sources to migrate. |

Each mapping:

| Key | Meaning |
| --- | --- |
| `name` | Short identifier used on the command line (`movie1`). |
| `label` | Readable name (`Movies 1`). |
| `type` | Category used by `--type`: `movies`, `tv`, `video`, `music`, `pictures`, `files`. |
| `source` | Folder on andy-pc. Normally a whole mounted disk. |
| `mountPoint` | Optional. The mounted disk containing `source`, when `source` is a folder inside it. Defaults to `source`. |
| `excludes` | Optional. Top-level folders of this source that another mapping handles. |
| `destination` | Absolute path on raid-pc inside `destinationMount`. |
| `uuid` | Optional. The filesystem UUID expected at `mountPoint`. |
| `enabled` | `true` to include the mapping in `--all` and `--type`. |

Several mappings may share one destination. The template merges `movie1` and
`movie2` into `Movies`, and `video1`–`video3` plus `/mnt/myVideo/TV` into `TV`.
Each mapping compares only its own source against the shared folder, so files
from other disks are ignored. If two disks hold the same path with different
content, the second disk reports a [conflict](#files-already-on-raid-pc) and
nothing is overwritten.

A folder inside a disk is migrated with `mountPoint`, as `myVideoTV` does for
`/mnt/myVideo/TV`. A mapping whose source contains another mapping's source must
exclude that folder (`"excludes": ["TV"]` on `myVideo`). Overlapping mappings
are rejected when the configuration is loaded.

The template ships with **every mapping disabled** and placeholder
destinations such as `<RAID_STORAGE_MOUNT>/Movies`. A placeholder is refused
before any network or data operation, so nothing can be migrated until the
raid-pc layout has been decided and written in.

## Initial setup

1. Install the local prerequisites on andy-pc: `rsync`, `jq`, `findmnt`
   (util-linux), coreutils and the `organiseMyProjects` Python package (for
   `logUtils.sh`).
2. Ensure raid-pc has `rsync` and the configured checksum tool.
3. Copy the template and replace the placeholders:

   ```bash
   mkdir -p ~/.config/migrateToRaid
   cp ~/bin/linuxBootstrap/configs/migrateToRaid/config.json ~/.config/migrateToRaid/
   ```

4. Enable mappings one at a time as their destinations are confirmed.

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
destination, the mounted filesystem, whether raid-pc is reachable, the source
size, the space available on raid-pc, how many entries are already identical
there, what would be copied and any conflicts. It also shows the exact `rsync`
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
- the destination exists or can be created, and is writable;
- the free space covers the data still to copy plus `minFreeBytesAfter`.

The copy uses rsync over SSH:

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
Source       Type      Copy         Verify         Source    Last check           Size
--------------------------------------------------------------------------------------
movie1       movies    complete     verified(full) retained  safe               3.2TiB
movie2       movies    partial      pending        retained  -                  3.6TiB
video1       tv        not run      -              retained  -                  3.5TiB

Migrated:  3.2TiB verified
Remaining: 7.1TiB used on unverified sources
```

A copy status of `interrupted` means a run stopped without recording its
outcome. Re-run it.

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
- raid-pc is reachable and the destination still matches the verified
  manifest.

**SAFE TO REMOVE DISK** additionally requires the
[raid-pc protection check](#parity-protection) to pass. Anything else prints
**NOT SAFE TO REMOVE DISK** with the reasons.

A mapping that covers only part of a disk (a `mountPoint` folder, or a mapping
with `excludes`) reports **SAFE TO REMOVE SOURCE FOLDER**. A **Disk** verdict
follows it, and that disk is safe only when every mapping on it is safe and
every top-level item on the disk belongs to one of those mappings. Anything
left over is listed.

`--check` exits with status 0 only when every verdict is safe.

### Parity protection

raid-pc starts with a few data disks and no parity. SnapRAID parity is added
once the extra disks are installed. Until parity exists and is in sync, losing
a raid-pc disk would lose migrated data that no longer has a copy on andy-pc.
So a copy can be **COPY VERIFIED** and still **NOT SAFE TO REMOVE DISK**.

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
├── protection.state                 last protection check
├── <name>.state                     current state of each mapping
├── <name>.history                   timestamped audit trail
├── <name>.manifest                  verified source manifest
├── <name>.conflicts                 destination conflicts to review
├── <name>-<timestamp>.rsync.log     every file rsync transferred
└── <name>-<timestamp>.removed       every file deleted from the source
```

`<name>.state` records the source and destination, source filesystem UUID,
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
