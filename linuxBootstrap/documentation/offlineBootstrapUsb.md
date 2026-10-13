# Offline bootable bootstrap USB

## Purpose

linuxBootstrap should support preparing a reusable USB stick that can take a machine from a blank system disk to an installed and bootstrapped Linux host without requiring LAN or Internet access during installation.

The first target is `raid-pc`. The design is deliberately profile-driven and distribution-aware so it can later be used for other supported hosts.

For the current `raid-pc` build, Pop!_OS 24.04 AMD64 is the preferred installation image because it is already used elsewhere in the environment and works with the existing APT-based linuxBootstrap model.

## User workflow

The USB has two responsibilities:

1. boot and install the supported Linux distribution;
2. provide linuxBootstrap and every package needed to apply the selected host profile offline.

The intended `raid-pc` workflow is:

1. On an Internet-connected preparation machine, download the required installation ISO.
2. Use Balena Etcher to write the ISO to the USB stick.
3. Inspect the resulting partition layout before making any further changes.
4. Create a separate writable data partition in trailing unused space, starting safely beyond the end of the ISO image.
5. Format the data partition as ext4 and label it `RAID-PC-DATA`.
6. Populate that partition using linuxBootstrap's bundle workflow.
7. Boot `raid-pc` from the USB and install Pop!_OS 24.04 to the dedicated 500 GB OS SSD.
8. Reboot into the installed system without requiring a LAN connection.
9. Mount the USB data partition.
10. Run linuxBootstrap against the offline bundle for the `raid-pc` host profile.
11. Review the normal safe-by-default preview and use `--confirm` only when ready to apply it.
12. Connect the host to the LAN after the base system is known-good, then verify networking and any network-dependent configuration.

Balena Etcher remains the preferred tool for writing the bootable installer image. linuxBootstrap does not replace Etcher or become an ISO-writing tool.

## Proven USB preparation method

A 32 GB Toshiba TransMemory USB stick was tested with a Pop!_OS 24.04 AMD64 ISO written by Balena Etcher.

Immediately after flashing, the device appeared as:

```text
/dev/sdm                         28.9G
├── /dev/sdm1                   3.3G  iso9660  Pop_OS 24.04 amd64
└── /dev/sdm2                     4M  vfat
```

`fdisk` reported the ISO image ending at sector `6881279`. Because hybrid ISO partition tables can be interpreted differently by different partitioning tools, linuxBootstrap documentation must not rely on a generic "free space" report alone.

For this tested image, the writable data partition was deliberately started at sector `6963200`, equivalent to 3400 MiB, leaving a safety margin beyond the end of the ISO image.

The resulting layout was:

```text
/dev/sdm
├── /dev/sdm1   3.3G
├── /dev/sdm2     4M  vfat
└── /dev/sdm3  25.6G
```

The intended final format is:

```text
32 GB USB
├── Pop!_OS 24.04 boot/install image
├── EFI boot data
└── RAID-PC-DATA                ext4
    └── linuxBootstrapBundle/
        ├── manifest.json
        ├── linuxMigration/
        │   └── linuxBootstrap/
        └── packages/
            └── *.deb
```

The data partition should be formatted with:

```bash
sudo mkfs.ext4 -L RAID-PC-DATA /dev/sdX3
```

where `/dev/sdX` has first been positively identified as the intended USB device.

The modified USB must be boot-tested after adding the data partition. Until that boot test succeeds, the preparation method is considered partially validated rather than complete.

## Important hybrid-ISO rule

Balena Etcher writes the hybrid ISO image directly to the device. The resulting ISO and EFI structures are not equivalent to a normal partitioned data disk.

Different tools may therefore describe the device differently. For example, one tool may show the ISO9660 image as a normal-looking partition while another reports much of that same region as free space.

Consequently:

- never create a new partition merely from the first "free space" position reported by a partition editor;
- determine the actual end of the written ISO image first;
- start the writable payload partition safely beyond that boundary;
- use explicit device identification before any partitioning or formatting operation;
- do not make linuxBootstrap itself automatically repartition removable media in the initial implementation.

This method should remain documented as image-specific until tested with other ISO releases.

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
- all required APT `.deb` packages;
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

For the current `raid-pc` bundle, expected target identity is conceptually:

```text
distribution: pop
release: 24.04
architecture: amd64
```

The implementation should derive and validate the actual operating-system identity rather than depend on these literal display strings.

Before an offline installation, linuxBootstrap must compare the manifest with the running system. A bundle for the wrong distribution release or architecture must fail before package installation.

## Package handling

The preferred implementation is a small local APT repository or another APT-compatible local package source rather than invoking `dpkg` over an unordered collection of files. This lets APT retain responsibility for dependency ordering and package state.

Bundle creation must resolve and download the complete dependency set while the preparation machine has Internet access. Offline installation must not silently fall back to network repositories.

A missing dependency is an error and should be reported before linuxBootstrap attempts unrelated configuration.

The package bundle must be built for the selected target distribution and release. A package set prepared for Debian must not be treated as interchangeable with one prepared for Pop!_OS/Ubuntu simply because both use APT.

## Safety requirements

The offline feature inherits linuxBootstrap's safe-by-default behaviour:

- `bundle` previews by default and requires `--confirm` before writing;
- `install --offline` previews configuration changes by default;
- package installation and configuration changes require `--confirm`;
- the USB preparation workflow must never repartition or format an arbitrary device implicitly;
- linuxBootstrap must validate the output path before writing a bundle;
- the target OS disk and storage disks remain outside the responsibility of bundle creation;
- the `raid-pc` storage safety boundary remains unchanged: normal bootstrap operations never format, repartition or automatically assign storage disks.

Balena Etcher is responsible for the explicitly user-selected bootable-media write. linuxBootstrap's initial implementation should operate only on an already-mounted writable payload partition/directory.

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

A new installer image is required only when the chosen installation image itself needs to change.

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

### Stage 4 - documented bootable USB preparation

- use Balena Etcher to write the selected hybrid installation ISO;
- identify the actual end of the written ISO image;
- create the writable payload partition only in trailing space beyond that boundary;
- format and label the payload partition `RAID-PC-DATA`;
- verify the partition can be mounted and written;
- boot-test the modified USB;
- test OS installation and subsequent payload access on representative hardware;
- document any image-specific offsets or constraints discovered during testing.

The currently tested Pop!_OS 24.04 image used sector `6963200` (3400 MiB) as the start of `RAID-PC-DATA`. This value must not be generalized to other installer images without measuring their actual written size first.

## Out of scope initially

The first implementation does not need to:

- replace Balena Etcher;
- create or write bootable ISO images;
- automatically repartition USB devices;
- automate the OS installer itself;
- embed credentials or secrets;
- provision or format `raid-pc` storage disks.

These boundaries keep the feature reusable while avoiding destructive removable-media and storage operations.
