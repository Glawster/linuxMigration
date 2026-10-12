# raid-pc bootstrap design

## Purpose

`raid-pc` is the rack-mounted Linux storage server. The linux-bootstrap project
must be able to converge its ordinary operating-system configuration repeatedly
without risking the contents of any storage disk.

The host name is `raid-pc`. The first implementation is deliberately limited to
the Phase 1 hardware described below. Later disk shelves and SAS HBAs are
expansion work, not prerequisites for the first installation.

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

The intended server installation is a minimal, headless Debian installation.
Desktop applications and workstation roles are not part of the `raid-pc`
profile.

The host profile should provide the normal server prerequisites, including SSH,
SMART monitoring, hardware/sensor inspection, Git and the packages needed by
the selected storage and NFS configuration.

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

## Initial storage model

The design target is mergerFS for a single data namespace with SnapRAID for
snapshot parity. This suits predominantly static media and allows disks to be
added progressively without rebuilding a conventional striped RAID array.

The initial five 4 TB HDDs are expected to become four data disks plus one
parity disk, subject to review during provisioning:

```text
/mnt/disks/data01
/mnt/disks/data02
/mnt/disks/data03
/mnt/disks/data04
/mnt/disks/parity01

/mnt/storage            mergerFS data namespace
```

This yields approximately 16 TB of raw data-disk capacity plus one 4 TB parity
disk before filesystem overhead. SnapRAID parity is snapshot parity and must
not be represented as real-time RAID protection.

The exact serial-to-role mapping must not be committed until the physical disks
have been inventoried on `raid-pc`.

## Network service

The combined storage namespace is intended to be exported to trusted LAN hosts
using NFS. NFS configuration should use the existing linux-bootstrap NFS
mechanisms rather than introducing a second configuration system.

Export policy and client permissions must be explicitly configured before the
share is enabled.

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

Future expansion may introduce an external SAS HBA and rack-mounted JBOD disk
shelf. The storage design must therefore avoid assumptions that data disks are
always motherboard SATA devices or that `/dev/sdX` names remain stable.

Adding an HBA/JBOD must extend the disk inventory and reviewed role mapping; it
must not require redesigning the host bootstrap or the mergerFS namespace.
