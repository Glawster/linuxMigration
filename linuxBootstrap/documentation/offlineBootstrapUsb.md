# Offline bootable bootstrap USB

## Purpose

linuxBootstrap should support preparing a reusable bootable installer image that can take a machine from a blank system disk to an installed and bootstrapped Linux host without requiring LAN or Internet access during installation.

The first target is `raid-pc`. The design is profile-driven and distribution-aware so it can later be used for other supported hosts.

For the current `raid-pc` build, Pop!_OS 22.04 AMD64 is the preferred installation image because it is already used elsewhere in the environment and works with the existing APT-based linuxBootstrap model.

## Design decision

The preferred single-stick design is a customised installer ISO containing the offline linuxBootstrap payload.

An earlier experiment wrote the stock Pop!_OS hybrid ISO with Balena Etcher and then added a writable partition in the unused trailing space. Although the partition could be created and formatted successfully, the modified stick did not boot: the boot process reported an unclean filesystem.

That approach is therefore rejected. linuxBootstrap must not modify the partition table of an Etcher-written hybrid installer image as part of the supported workflow.

Instead, the bootstrap payload is added to a copy of the installer ISO before the image is written to USB. Balena Etcher then writes the completed custom ISO as one immutable bootable image.

## User workflow

The intended `raid-pc` workflow is:

1. On an Internet-connected preparation machine, obtain the supported Pop!_OS 22.04 AMD64 source ISO.
2. Build the offline linuxBootstrap bundle for `raid-pc`.
3. Remaster a copy of the source ISO and add the bundle under a dedicated `raid-pc` directory.
4. Rebuild the ISO while preserving the original BIOS/UEFI/hybrid boot behaviour.
5. Validate the resulting ISO and its embedded bootstrap payload.
6. Use Balena Etcher to write the custom ISO to the USB stick.
7. Boot-test the USB.
8. Boot `raid-pc` from the USB and install Pop!_OS 22.04 to the dedicated 500 GB OS SSD.
9. Reboot into the installed system without requiring LAN or Internet access.
10. Mount or otherwise access the installer media.
11. Run linuxBootstrap against the embedded offline bundle for the `raid-pc` host profile.
12. Review the normal safe-by-default preview and use `--confirm` only when ready to apply it.
13. Connect the host to the LAN after the base system is known-good, then verify networking and any network-dependent configuration.

Balena Etcher remains responsible only for writing the completed ISO to the explicitly selected USB device. linuxBootstrap does not directly write or repartition USB devices.

## Custom ISO layout

The conceptual image is:

```text
raid-pc-popos-22.04-amd64.iso
├── original Pop!_OS installer/live content
├── original BIOS/UEFI boot structures
└── raid-pc/
    └── linuxBootstrapBundle/
        ├── manifest.txt
        ├── SHA256SUMS
        ├── linuxBootstrap/
        └── packages/
            ├── Packages
            ├── Packages.gz
            └── *.deb
```

The bootstrap payload is read-only on the installer media. It does not need a writable USB filesystem during installation or bootstrap.

The source ISO must never be modified in place. Image creation works from a copy or extracted working tree and produces a new output ISO.

## Proposed command line

Bundle creation remains a separate operation so it can be tested independently:

```bash
./bootstrap.sh bundle --profile raid-pc --output ./build/raid-pc-bundle
```

The command previews by default. Writes require confirmation:

```bash
./bootstrap.sh bundle --profile raid-pc \
    --output ./build/raid-pc-bundle \
    --confirm
```

A second command builds the customised installer image:

```bash
./bootstrap.sh image \
    --profile raid-pc \
    --iso /path/to/pop-os_22.04_amd64_intel_58.iso \
    --bundle ./build/raid-pc-bundle/linuxBootstrapBundle \
    --output ./build/raid-pc-popos-22.04-amd64.iso
```

Image creation also previews by default and requires confirmation before creating or replacing output files:

```bash
./bootstrap.sh image \
    --profile raid-pc \
    --iso /path/to/pop-os_22.04_amd64_intel_58.iso \
    --bundle ./build/raid-pc-bundle/linuxBootstrapBundle \
    --output ./build/raid-pc-popos-22.04-amd64.iso \
    --confirm
```

The `bundle` and `image` command lines above are implemented and were used for the first `raid-pc` installation-media build.

## Running the embedded bootstrap

After Pop!_OS is installed, the installer USB is inserted or remains available and its ISO filesystem is mounted. The operator then runs linuxBootstrap from the embedded bundle, conceptually:

```bash
cd /media/$USER/<installer-label>/raid-pc/linuxBootstrapBundle/linuxMigration/linuxBootstrap
./bootstrap.sh install --profile raid-pc --offline
./bootstrap.sh install --profile raid-pc --offline --confirm
```

The implementation must not depend on a fixed desktop automount path. Documentation can show an example, while bootstrap discovery should accept an explicit bundle path or reliably locate the embedded manifest.

## Bundle contents

A bundle must contain enough information to install the selected profile without reaching an Internet repository. At minimum it contains:

- the linuxMigration/linuxBootstrap source required to run the selected profile;
- the selected host profile and inherited role profiles;
- all required APT `.deb` packages;
- the complete dependency closure required by those packages;
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

`manifest.txt` currently records:

- bundle format version;
- creation timestamp;
- selected host profile;
- inherited profiles;
- target distribution;
- target distribution release;
- target architecture;
- requested top-level package list;
- resolved package list and versions.

`SHA256SUMS` records payload integrity separately. Source-ISO identity and bootstrap revision remain desirable future manifest metadata rather than current fields.

For the current `raid-pc` bundle, expected target identity is conceptually:

```text
distribution: pop
release: 22.04
architecture: amd64
```

The implementation should derive and validate the actual operating-system identity rather than depend on these literal display strings.

Stage 5 must compare this metadata with the running system before package installation. A bundle for the wrong distribution release or architecture must fail.

## Package handling

The preferred implementation is a small local APT repository or another APT-compatible local package source rather than invoking `dpkg` over an unordered collection of files. This lets APT retain responsibility for dependency ordering and package state.

Bundle creation must resolve and download the complete dependency set while the preparation machine has Internet access. Offline installation must not silently fall back to network repositories.

A missing dependency is an error and should be reported before linuxBootstrap attempts unrelated configuration.

The package bundle must be built for the selected target distribution and release. A package set prepared for Debian must not be treated as interchangeable with one prepared for Pop!_OS/Ubuntu simply because both use APT.

## ISO remastering requirements

The custom-image implementation must preserve the boot behaviour of the source Pop!_OS ISO. Merely copying files into an extracted directory and creating a generic ISO9660 image is insufficient.

The image builder must:

- inspect and validate the source ISO before modifying anything;
- preserve the source image's BIOS/UEFI/hybrid boot structures and required boot files;
- add only the managed bootstrap payload to the installer filesystem;
- produce a new output ISO rather than changing the source image;
- generate or update checksums required by the installer image where applicable;
- verify that the embedded manifest and package payload can be read back from the completed ISO;
- record the source ISO checksum and resulting custom ISO checksum;
- fail rather than emit an image when required boot metadata cannot be reproduced safely.

The exact remastering commands and tooling must be established from inspection of the actual Pop!_OS 22.04 source ISO and covered by tests. The design must not hard-code boot parameters copied from an unrelated Debian or Ubuntu image.

## Safety requirements

The offline feature inherits linuxBootstrap's safe-by-default behaviour:

- `bundle` previews by default and requires `--confirm` before writing;
- `image` previews by default and requires `--confirm` before creating the custom ISO;
- `install --offline` previews configuration changes by default;
- package installation and configuration changes require `--confirm`;
- the image workflow never writes directly to a block device;
- linuxBootstrap validates source and output paths before writing;
- the original installer ISO remains unchanged;
- an existing output ISO is not silently overwritten;
- the target OS disk and storage disks remain outside the responsibility of bundle/image creation;
- the `raid-pc` storage safety boundary remains unchanged: normal bootstrap operations never format, repartition or automatically assign storage disks.

Balena Etcher remains an explicit manual step after image generation. The operator selects the target USB in Etcher.

## Network-independent boundary

A successful offline run means the base profile can be applied without LAN or Internet access. Configuration that inherently requires a live remote service must either:

- be represented locally in the bundle; or
- be deferred and clearly reported as pending until networking is available.

No operation should hang or unexpectedly attempt Internet access when `--offline` is selected.

For `raid-pc`, this makes it possible to install and inspect the server on the bench before connecting it to the home LAN.

## First end-to-end validation

The first `raid-pc` media build and installation was completed with the Pop!_OS 22.04 Intel/AMD ISO `pop-os_22.04_amd64_intel_58.iso`.

The generated image was verified to retain legacy BIOS boot through `/isolinux/isolinux.bin`, UEFI boot through `/boot/grub/efi.img`, and hybrid MBR/GPT metadata. The embedded `/raid-pc/linuxBootstrapBundle` payload was present and its `SHA256SUMS` validation passed.

The image was written with Balena Etcher and booted successfully. Pop!_OS 22.04 was then installed to the dedicated 500 GB SSD. With the machine still disconnected from the LAN, the bundle was copied to `/opt/linuxBootstrap` and used as the only APT source. The fresh installation successfully installed `git`, `openssh-server`, `smartmontools`, `lm-sensors`, `nfs-kernel-server`, `mergerfs` and `snapraid` together with their required dependencies without Internet access.

Two implementation details were confirmed during the test. The active `file:` repository should not live below a private home directory because APT normally reads repository metadata as the restricted `_apt` user. Also, `--no-download` must not be used for the real install from a `file:` source: APT still needs to acquire/copy the selected `.deb` files from the local repository. Network repositories must instead be disabled explicitly.

This validates bundle creation, dependency closure, local APT indexing, ISO remastering, bootability and real offline package installation. Automating the post-install local-repository setup remains Stage 5 work.

## Refreshing the installation media

The installer ISO and bootstrap payload can have different lifecycles. If only linuxBootstrap or package versions change, the source Pop!_OS ISO can be reused to generate a fresh custom ISO.

The workflow is:

```text
stock Pop!_OS ISO
        +
current raid-pc offline bundle
        |
        v
new custom raid-pc ISO
        |
        v
Balena Etcher
        |
        v
USB
```

The generated ISO is a build artefact and should not be committed to the repository.

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

### Stage 3 - custom image planning and inspection

- add the `image` command in preview mode;
- inspect the supplied Pop!_OS ISO;
- identify the boot method and metadata required to reproduce it;
- validate source ISO identity and checksum;
- calculate the intended embedded bundle location;
- report required image-building tools;
- add command-double tests without creating an ISO.

### Stage 4 - custom image creation

- extract or stage the source ISO safely;
- embed the validated offline bundle;
- rebuild the bootable hybrid ISO while preserving Pop!_OS boot behaviour;
- verify the completed ISO filesystem and embedded manifest;
- calculate and report the output checksum;
- boot-test the image after writing it with Balena Etcher.

### Stage 5 - offline installation

- add `install --offline` and explicit bundle-path handling;
- discover and validate the embedded bundle;
- reject distribution/release/architecture mismatches;
- configure APT to use only the embedded local package source;
- apply the existing profile workflow from local resources;
- report deferred network-only actions explicitly.

## Rejected approach: trailing writable partition

The following method was tested and rejected:

1. write the Pop!_OS 22.04 hybrid ISO to a 32 GB Toshiba TransMemory stick using Balena Etcher;
2. observe the approximately 3.3 GB ISO image and 4 MB EFI structure;
3. create a third partition beginning at sector `6963200` (3400 MiB), beyond the reported end of the ISO image;
4. format that partition for `RAID-PC-DATA`.

The resulting USB did not boot successfully and reported an unclean filesystem. The experiment demonstrated that apparently unused trailing capacity on an Etcher-written hybrid ISO must not be assumed safe for an additional partition.

This result is retained here so the failed design is not accidentally reintroduced later.

## Out of scope initially

The first implementation does not need to:

- replace Balena Etcher or write directly to USB devices;
- automatically repartition removable media;
- automate the Pop!_OS installer itself;
- automatically execute linuxBootstrap during OS installation;
- embed credentials or secrets;
- provision or format `raid-pc` storage disks.

These boundaries keep the feature reusable while avoiding destructive removable-media and storage operations.