# Roadmap

linuxMigration sequencing and priorities. Current increment status is kept in
[currentIncrement.md](currentIncrement.md).

## linuxBootstrap

### Foundation

- [x] Profile composition and host inheritance
- [x] YAML-driven Apt, Flatpak, and Snap package installer abstraction
- [x] Git, SSH-directory, hostname, and service configuration
- [x] Dry-run-by-default execution and summary
- [x] Dependency-free tests
- [x] Validate all supported profile keys and reject misspellings
- [ ] Deduplicate merged lists before module execution

### Package and development tooling

- [x] Flatpak backend and Flathub remote management
- [ ] Snap, Homebrew, Pip, Cargo, and npm backends
- [ ] Homebrew, Pip, Cargo, and npm package backends
- [ ] Repository definitions with destination and branch policy
- [ ] VS Code extension management
- [ ] Miniconda, Docker, and Podman modules

### Desktop and specialist roles

- [ ] GNOME settings, fonts, wallpapers, and mount points
- [ ] Gaming launchers, ProtonUp-Qt, and controller configuration
- [ ] SteamVR and VR device rules
- [ ] Media services and hardware acceleration
- [ ] Samba configuration
- [x] NFS exports and persistent NFSv4 mounts

### Storage migration

- [x] `migrateToRaid`: copy, verify and record andy-pc storage on raid-pc ([001](requirements/features/001-raidMigration.md))
- [x] `migrateToRaid` local destination for personal media on `/mnt/media` ([ADR 002](adr/002-localMigrationDestination.md))
- [x] `migrateToRaid` run on raid-pc for disks attached there ([ADR 003](adr/003-migrateOnRaidPc.md))
- [ ] Install the SkyHawk as `/mnt/media` and migrate the `myPictures` and `myVideo` remainders
- [ ] Migrate the old video1 disk (USB on raid-pc) into the pool TV folder once the pool exists
- [ ] Update the media drive mappings (`profiles/media.yaml`) for `/mnt/media` and the retired `/mnt/video1`
- [ ] Confirm the raid-pc storage layout and enable mappings
- [ ] Configure the raid-pc parity protection check once SnapRAID parity is synced
- [ ] Add `raid-pc` to the managed SSH host configuration
- [ ] Declare `rsync` and `jq` in the andy-pc and raid-server profiles

### Operations

- [x] Subcommand CLI with install, update, status, and profile operations
- [x] Managed, unmanaged, and system package update reporting
- [ ] Rich `status` output with per-module health categories
- [x] Preview-first global Git configuration capture into an explicit profile
- [ ] Additional reviewed master-host capture domains
- [ ] `--repair` using the same inspection paths as normal execution
- [ ] Cron and systemd user-service management
- [ ] NetworkManager connection selection and static addressing
- [ ] Integration tests in a disposable Pop!_OS-compatible virtual machine
