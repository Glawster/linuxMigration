# raid-pc bootstrap design

## Purpose

`raid-pc` is the rack-mounted Linux storage server. The linux-bootstrap project
must be able to converge its ordinary operating-system configuration repeatedly
without risking the contents of any storage disk.

The host name is `raid-pc`. The first implementation is deliberately limited to
the Phase 1 hardware described below. Later disk shelves and SAS HBAs are
expansion work, not prerequisites for the first installation. A SAS HBA with two
more data disks has since been added; see [Storage model](#storage-model).

## Phase 1 hardware baseline

- one 500 GB SSD dedicated to the operating system;
- five 4 TB 3.5-inch HDDs for storage;
- all five storage HDDs attached directly to motherboard SATA ports;
- no LSI HBA is required for Phase 1;
- the operating system and storage data must not share a disk.

The bootstrap must discover the actual hardware rather than rely on Linux
`/dev/sdX` ordering. Persistent storage identity must use serial numbers,
filesystem UUIDs and/or filesystem labels as appropriate.

## Operating system

The installed operating system is Pop!_OS 22.04 AMD64 (Intel/AMD image) on the dedicated 500 GB SSD. The machine is intended to run headless after installation; desktop applications and workstation roles are not part of the `raid-pc` profile.

The host profile provides the normal server prerequisites, including SSH, SMART monitoring, hardware/sensor inspection, Git and the packages needed by the selected storage and NFS configuration. The base package set has been validated by installing it on a fresh Pop!_OS 22.04 system from the offline bootstrap bundle with the LAN disconnected.

## Safety boundary

Normal linux-bootstrap operations are non-destructive with respect to storage.

`install`, `update` and `status` must never:

- format a disk;
- create or remove a filesystem;
- alter a partition table;
- assign a discovered disk to a data or parity role automatically;
- overwrite storage configuration merely because Linux device names changed.

Storage provisioning is a separate workflow. Its default operation is a
read-only plan. Any destructive action must require an explicit confirmation
after displaying the disks concerned by persistent identity.

This separation means the ordinary host bootstrap can safely be rerun after an
OS reinstall or upgrade.

## Storage discovery

The storage workflow must be able to report, at minimum, for each candidate
disk:

- Linux device path (informational only);
- model;
- serial number;
- capacity;
- transport/controller where available;
- filesystem/partition state;
- filesystem UUID/label where present;
- SMART health and relevant warning state;
- proposed role, if a reviewed storage configuration already assigns one.

The 500 GB system SSD must be clearly distinguished from candidate storage
HDDs. Discovery must not infer that every non-root disk is safe to erase.

## Storage model

The design uses mergerFS for a single data namespace with SnapRAID for
snapshot parity. This suits predominantly static media and allows disks to be
added progressively without rebuilding a conventional striped RAID array.

The original five 4 TB HDDs became four data disks plus one parity disk, and
all five passed extended SMART self-tests before assignment. Two reused disks
were later added as `data05` and `data06` on the [SAS HBA](#sas-hba), after
passing a SMART health check with no reallocated, pending or uncorrectable
sectors:

| Role | Disk | Notes |
| --- | --- | --- |
| `parity01` | Seagate IronWolf `ST4000VN006` | CMR, young; preferred for parity because SnapRAID sync rewrites parity across the whole disk |
| `data01`–`data05` | three WD Red `WD40EFAX` and two Seagate BarraCuda `ST4000DM004` | SMR; mostly static media, written once, read often |
| `data06` | Seagate Barracuda `ST2000DM001` | 2 TB; reused old `video1` disk. This model has a poor reliability record, so watch its SMART state |

Roles are assigned by serial number, never by `/dev/sdX`. Device names change
when disks are added: fitting the HBA moved the motherboard disks from
`sda`-`sdf` to `sdc`-`sdh`. Confirm roles on raid-pc with
`lsblk -o NAME,MODEL,SERIAL,SIZE,TRAN,MOUNTPOINT` before provisioning:

| Role | Model | Serial | Attached to |
| --- | --- | --- | --- |
| `parity01` | `ST4000VN006-3CW104` | `WW662Z03` | motherboard SATA |
| `data01` | `WD40EFAX-68JH4N0` | `WD-WX62D105VVJ9` | motherboard SATA |
| `data02` | `WD40EFAX-68JH4N0` | `WD-WX22D10FNVCU` | motherboard SATA |
| `data03` | `WD40EFAX-68JH4N0` | `WD-WX22D10FNUEA` | motherboard SATA |
| `data04` | `ST4000DM004-2CV104` | `ZFN4TS8H` | motherboard SATA |
| `data05` | `ST4000DM004-2CV104` | `ZFN4TRE1` | SAS HBA |
| `data06` | `ST2000DM001-1CH164` | `W1E2HY9S` | SAS HBA |

The layout:

```text
/mnt/data01
/mnt/data02
/mnt/data03
/mnt/data04
/mnt/data05
/mnt/data06
/mnt/parity01

/mnt/storage            mergerFS data namespace
```

This yields approximately 22 TB of raw data-disk capacity plus one 4 TB parity
disk before filesystem overhead. One parity disk recovers from one failed disk
at a time, across all six data disks. SnapRAID parity is snapshot parity and
must not be represented as real-time RAID protection.

Each disk is mounted by filesystem UUID in `/etc/fstab` with `nofail`. The
parity disk must be at least as large as the largest data disk, so data disks
keep the ext4 default of 5% reserved space, as the parity disk does.

### SAS HBA

A Broadcom/LSI SAS2008 HBA in the main PCIe x16 slot (running at x8, 5 GT/s)
provides the extra disk ports. It runs firmware 20.00.07.00 and uses the
`mpt3sas` driver; the driver reports no RAID capability, so disks appear
individually as SnapRAID needs. Check it with:

```bash
lspci -nn | grep -i sas
lsblk -d -o NAME,SIZE,TRAN,MODEL,SERIAL,HCTL
```

Disks behind the HBA show a transport of `sas` even when they are SATA disks.

### Adding a data disk

The steps are run by hand on raid-pc, and identify the disk only by its
`/dev/disk/by-id` path:

1. Check SMART health, and confirm that nothing on the disk is still needed.
2. Clear old signatures, stopping any `md` arrays Linux assembled from it first.
3. Create one partition and an ext4 filesystem with the next `dataNN` label.
4. Add its UUID to `/etc/fstab`, and its mount point to the mergerFS line.
5. Add a `data dN /mnt/dataNN/` line to `/etc/snapraid.conf`.
6. Reboot to bring up the pool with the new disk, because NFS exports it.
7. Run `sudo snapraid sync` to protect whatever has been added since the last
   sync.

New files go to the disk with the most free space (`category.create=mfs`), so a
newly added disk receives writes first until the disks level out.

Provisioning (partitioning, filesystems, mergerFS and SnapRAID configuration)
is a separate, explicitly confirmed workflow. `migrateToRaid` does not
provision any disk.

## Network service

The combined storage namespace is intended to be exported to trusted LAN hosts
using NFS. NFS configuration should use the existing linux-bootstrap NFS
mechanisms rather than introducing a second configuration system.

Export policy and client permissions must be explicitly configured before the
share is enabled.

## Network and media placement

`raid-pc` will connect by wired Ethernet directly to the LAN/router. The design
assumes Gigabit Ethernet where available. A 1 Gb/s link normally delivers roughly
100-115 MB/s for large sequential transfers; a true 100 Mb/s Ethernet link would
be limited to roughly 11-12 MB/s and should be treated as insufficient for the
intended bulk-media role.

The router should reserve a stable DHCP address for `raid-pc`. The bootstrap
should validate that expected address rather than forcing a local static address,
matching the existing network-management model.

The storage pool is exported whole:

```text
raid-pc:/mnt/storage
```

On andy-pc it is mounted at:

```text
/mnt/raid
```

so the pool's `Movies` and `TV` folders are `/mnt/raid/Movies` and
`/mnt/raid/TV`. The first consumers are expected to be:

- organiseMyVideo (OMV), which should treat `/mnt/raid/Movies` and
  `/mnt/raid/TV` as other managed media locations rather than as a special
  network-only case;
- Media Center Master (MCM), whose Wine drives `R:` and `T:` map to
  `/mnt/raid/Movies` and `/mnt/raid/TV` (see [Media drives](mediaCenterMaster.md#media-drives)).

The export is declared in `profiles/hosts/raid-pc.yaml` for the local network
(`192.168.1.0/24`) with an explicit `fsid`, which a FUSE filesystem such as
mergerFS needs. The andy-pc mount is declared in `profiles/hosts/andy-pc.yaml`
and uses the linux-bootstrap NFS mechanism with systemd automount.

### Initial migration strategy

The first migration should move approximately half of the existing video library
to `raid-pc`, while keeping the most frequently used material local to
`andy-pc`. This is a placement/tiering decision rather than duplication: each
media folder should have one authoritative location unless a separate backup
policy says otherwise.

The intended model is therefore:

```text
andy-pc local storage        raid-pc storage
---------------------        ---------------
frequently used media        less frequently used media
active/recent content        older/archive-style content
         \                         /
          \---- OMV + MCM --------/
```

OMV and MCM must be able to see both locations at the same time so existing
catalogue and organisation workflows can span local and remote media. Migration
must be performed by complete media folders, not by splitting one title across
multiple stores.

raid-pc is the bulk destination for Movies, TV and archive media. Personal
Pictures and personal/home Video do not move to raid-pc: they stay on andy-pc
on the internal `/mnt/media` disk.

Copying, verification and source removal to both are performed by
`migrateToRaid`, run on andy-pc; see the [migration guide](migrateToRaid.md).
A disk attached directly to raid-pc is copied into the pool by hand with rsync
on raid-pc. The old 2 TB video1 disk was copied this way from `/mnt/oldVideo1`,
then wiped and reused as `data06`.

## Maintenance

The eventual server configuration should provide systemd-managed maintenance
for:

- SMART monitoring and scheduled tests;
- disk-temperature/health visibility;
- SnapRAID sync;
- SnapRAID scrub;
- missing/failed disk detection;
- storage-capacity reporting;
- actionable failure logging.

The first implementation may stage these capabilities, but storage health must
be inspectable before the machine is treated as the authoritative store.

## Expansion boundary

Future expansion may introduce a rack-mounted JBOD disk shelf. The storage
design must therefore avoid assumptions that data disks are always motherboard
SATA devices or that `/dev/sdX` names remain stable.

Adding a JBOD or another HBA must extend the disk inventory and reviewed role
mapping; it must not require redesigning the host bootstrap or the mergerFS
namespace.
