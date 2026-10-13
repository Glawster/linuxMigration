# Offline bootable bootstrap USB

## Purpose

linuxBootstrap should support preparing a reusable USB stick that can take a machine from a blank system disk to an installed and bootstrapped Linux host without requiring LAN or Internet access during installation.

The first target is `raid-pc`, using Debian 13 on its dedicated 500 GB SSD, but the design is deliberately profile-driven so it can later be used for other supported hosts.

## User workflow

The USB has two responsibilities:

1. boot and install the supported Linux distribution;
2. provide linuxBootstrap and every package needed to apply the selected host profile offline.

The intended `raid-pc` workflow is:

1. On an Internet-connected preparation machine, download the appropriate Debian installer ISO.
2. Use Rufus to create the bootable installer USB.
3. Keep or create a separate writable data partition on the same USB for the bootstrap payload.
4. Populate that data partition using linuxBootstrap's bundle workflow.
5. Boot `raid-pc` from the USB and install Debian 13 to the 500 GB OS SSD.
6. Reboot into the installed Debian system without requiring a LAN connection.
7. Mount the USB data partition.
8. Run linuxBootstrap against the offline bundle for the `raid-pc` host profile.
9. Review the normal safe-by-default preview and use `--confirm` only when ready to apply it.
10. Connect the host to the LAN after the base system is known-good, then verify networking and any network-dependent configuration.

Rufus remains the preferred tool for writing the bootable installer. linuxBootstrap does not need to replace Rufus or become an ISO-writing tool.

## USB layout

The conceptual layout is:

```text
USB stick
├── bootable Debian installer area
└── RAID-PC-DATA (writable partition)
    └── linuxBootstrapBundle/
        ├── manifest.json
        ├── linuxMigration/
        │   └── linuxBootstrap/
        └── packages/
            └── *.deb
```

The installer area and writable payload area are deliberately separate. Updating linuxBootstrap or refreshing packages should not require rewriting the Debian installer image.

The exact partitioning procedure depends on how Rufus writes the selected Debian image and must be documented and tested before it is treated as a supported preparation workflow. The implementation must not assume that unused capacity after writing an ISO is automatically writable.

## Proposed command line

Bundle creation should be explicit and safe by default. A target profile determines the package set:

```bash
./bootstrap.sh bundle --profile raid-pc --output /media/$USER/RAID-PC-DATA
```

The command should preview what it intends to place on the destination. Consistent with the rest of linuxBootstrap, writes occur only with confirmation:

```bash
./bootstrap.sh bundle --profile raid-pc \
    --output /media/$USER/RAID-PC-DATA \
    --confirm
```

On the target machine:

```bash
cd /media/$USER/RAID-PC-DATA/linuxBootstrapBundle/linuxMigration/linuxBootstrap
./bootstrap.sh install --profile raid-pc --offline
./bootstrap.sh install --profile raid-pc --offline --confirm
```

The exact CLI spelling is a design target until implementation and tests establish the final interface.

## Bundle contents

A bundle must contain enough information to install the selected profile without reaching an Internet repository. At minimum it contains:

- the linuxMigration/linuxBootstrap source required to run the selected profile;
- the selected host profile and inherited role profiles;
- all required Debian `.deb` packages;
- package dependencies required by those packages;
- a machine-readable manifest describing the bundle;
- checksums for bundled payload files.

For `raid-pc`, the current `raid-server` profile includes packages such as:

- `git`;
- `openssh-server`;
- `smartmontools`;
- `lm-sensors`;
- `nfs-kernel-server`;
- `mergerfs`;
- `snapraid`.

The dependency closure, rather than only these top-level packages, must be available offline.

## Manifest

`manifest.json` should record at least:

- bundle format version;
- creation timestamp;
- selected host profile;
- inherited profiles;
- target distribution;
- target distribution release;
- target architecture;
- linuxBootstrap source revision/commit;
- package list and versions;
- payload checksums.

Before an offline installation, linuxBootstrap must compare the manifest with the running system. A bundle for the wrong distribution release or architecture must fail before package installation.

## Package handling

The preferred implementation is a small local APT repository or another APT-compatible local package source rather than invoking `dpkg` over an unordered collection of files. This lets APT retain responsibility for dependency ordering and package state.

Bundle creation must resolve and download the complete dependency set while the preparation machine has Internet access. Offline installation must not silently fall back to network repositories.

A missing dependency is an error and should be reported before linuxBootstrap attempts unrelated configuration.

## Safety requirements

The offline feature inherits linuxBootstrap's safe-by-default behaviour:

- `bundle` previews by default and requires `--confirm` before writing;
- `install --offline` previews configuration changes by default;
- package installation and configuration changes require `--confirm`;
- the USB preparation workflow must never repartition or format an arbitrary device implicitly;
- linuxBootstrap must validate the output path before writing a bundle;
- the target OS disk and storage disks remain outside the responsibility of bundle creation;
- the `raid-pc` storage safety boundary remains unchanged: normal bootstrap operations never format, repartition or automatically assign storage disks.

Rufus is responsible for the explicitly user-selected bootable-media write. linuxBootstrap's initial implementation should operate only on an already-mounted writable payload partition/directory.

## Network-independent boundary

A successful offline run means the base profile can be applied without LAN or Internet access. Configuration that inherently requires a live remote service must either:

- be represented locally in the bundle; or
- be deferred and clearly reported as pending until networking is available.

No operation should hang or unexpectedly attempt Internet access when `--offline` is selected.

For `raid-pc`, this makes it possible to install and inspect the server on the bench before connecting it to the home LAN.

## Refreshing a reusable USB

The bootable installer and bootstrap payload have different lifecycles. A normal refresh should update only the writable payload partition:

```bash
./bootstrap.sh bundle --profile raid-pc \
    --output /media/$USER/RAID-PC-DATA \
    --confirm
```

A new Debian installer image is required only when the chosen installation image itself needs to change.

Bundle refresh should replace its own managed bundle directory atomically where practical and must not delete unrelated files from the USB partition.

## Implementation stages

### Stage 1 - bundle planning

- add the `bundle` command;
- resolve host and inherited profiles;
- calculate required APT packages;
- determine target distribution/release/architecture;
- preview the proposed bundle;
- add tests using command doubles.

### Stage 2 - bundle creation

- download the complete package dependency closure;
- create the local package source;
- copy the required linuxBootstrap source;
- write manifest and checksums;
- validate the finished bundle;
- preserve safe-by-default `--confirm` behaviour.

### Stage 3 - offline installation

- add `install --offline`;
- discover and validate the bundle;
- reject distribution/release/architecture mismatches;
- configure APT to use the bundle without contacting network repositories;
- apply the existing profile workflow from local resources;
- report deferred network-only actions explicitly.

### Stage 4 - documented Rufus preparation

- verify the chosen Debian installer image with Rufus;
- establish a repeatable method for retaining/creating the writable payload partition;
- document the Windows preparation steps;
- test boot, Debian installation and subsequent payload access on representative hardware.

## Out of scope initially

The first implementation does not need to:

- replace Rufus;
- create or write bootable ISO images;
- automatically repartition USB devices;
- automate the Debian installer itself;
- embed credentials or secrets;
- provision or format `raid-pc` storage disks.

These boundaries keep the feature reusable while avoiding destructive removable-media and storage operations.