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
- [ ] Install the SkyHawk as `/mnt/media` and migrate the `myPictures` and `myVideo` remainders
- [ ] Copy the old video1 disk (USB on raid-pc) into the pool TV folder by hand ([ADR 004](adr/004-migrateOnlyOnAndyPc.md))
- [ ] Update the media drive mappings (`profiles/media.yaml`) for `/mnt/media` and the retired `/mnt/video1`
- [x] Confirm the raid-pc storage layout (`/mnt/storage`)
- [ ] Enable the raid-pc mappings
- [ ] Rename `/mnt/movie1` and `/mnt/video2` to `/mnt/movies` and `/mnt/video`
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
