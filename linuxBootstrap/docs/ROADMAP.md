# Roadmap

## Foundation

- [x] Profile composition and host inheritance
- [x] Apt package presence checks and installation
- [x] Git, SSH-directory, hostname, and service configuration
- [x] Dry-run-by-default execution and summary
- [x] Dependency-free tests
- [x] Validate all supported profile keys and reject misspellings
- [ ] Deduplicate merged lists before module execution

## Package and development tooling

- [x] Flatpak backend and Flathub remote management
- [ ] Snap, Homebrew, Pip, Cargo, and npm backends
- [ ] Repository definitions with destination and branch policy
- [ ] VS Code extension management
- [ ] Miniconda, Docker, and Podman modules

## Desktop and specialist roles

- [ ] GNOME settings, fonts, wallpapers, and mount points
- [ ] Gaming launchers, ProtonUp-Qt, and controller configuration
- [ ] SteamVR and VR device rules
- [ ] Media services and hardware acceleration
- [ ] Samba and NFS configuration

## Operations

- [x] Subcommand CLI with install, update, status, and profile operations
- [x] Managed, unmanaged, and system package update reporting
- [ ] Rich `status` output with per-module health categories
- [ ] Master-host configuration capture
- [ ] `--repair` using the same inspection paths as normal execution
- [ ] Cron and systemd user-service management
- [ ] NetworkManager connection selection and static addressing
- [ ] Integration tests in a disposable Pop!_OS-compatible virtual machine
