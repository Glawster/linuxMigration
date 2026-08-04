#!/usr/bin/env bash

packagesApply() {
    local manager="$1"
    shift
    (($#)) || return 0
    case "$manager" in
        apt) packagesAptApply "$@" ;;
        flatpak) packagesFlatpakApply "$@" ;;
        *) logError "unsupported package manager: $manager"; return 2 ;;
    esac
}

packagesAptApply() {
    commandRequire dpkg-query
    local package
    for package in "$@"; do
        if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
            itemSkip "apt package already installed: $package"
        else
            changeRun "install apt package: $package" sudo apt-get install -y "$package"

    packagesManagerRequire "$manager"
    local package
    for package in "$@"; do
        if packagesPackageInstalled "$manager" "$package"; then
            itemSkip "$manager package already installed: $package"
        else
            packagesPackageInstall "$manager" "$package"
        fi
    done
}

packagesFlatpakApply() {
    local package
    if ! command -v flatpak >/dev/null 2>&1; then
        if [[ "${dryRun:-1}" == 1 ]]; then
            for package in "$@"; do
                changeRun "install system Flatpak: $package" flatpak install --system --noninteractive -y flathub "$package"
            done
            return 0
        fi
        logError "required command not found after apt package processing: flatpak"
        return 127
    fi
    packagesFlatpakRemoteEnsure
    for package in "$@"; do
        if flatpak info --system "$package" >/dev/null 2>&1; then
            itemSkip "system Flatpak already installed: $package"
        else
            changeRun "install system Flatpak: $package" flatpak install --system --noninteractive -y flathub "$package"
        fi
    done
}

packagesFlatpakRemoteEnsure() {
    if flatpak remote-list --system --columns=name 2>/dev/null | grep -Fxq flathub; then
        itemSkip "system Flatpak remote already configured: flathub"
    else
        changeRun "configure system Flatpak remote: flathub" sudo flatpak remote-add --system --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
    fi
}

packagesUnsupportedReport() {
    ((${#profileSnapPackages[@]} == 0)) || logWarning "Snap packages are declared but support is planned: ${profileSnapPackages[*]}"
}

packagesUpdate() {
    local -a managedApt=("$@")
    packagesUpdateMetadata
    packagesAptUpdatesReport "${managedApt[@]}"
    changeRun "upgrade installed apt packages" sudo apt-get upgrade -y
    packagesFlatpakUpdatesReport
    if command -v flatpak >/dev/null 2>&1; then
        changeRun "update installed system Flatpaks" flatpak update --system --noninteractive -y
    fi
}

packagesUpdateMetadata() {
    changeRun "refresh apt package metadata" sudo apt-get update
    if command -v flatpak >/dev/null 2>&1; then
        changeRun "refresh system Flatpak metadata" flatpak update --system --appstream --noninteractive
    fi
}

packagesAptUpdatesReport() {
    local -a managedPackages=("$@") candidates=() manualPackages=()
    local package category
    local -A managed=() manual=()
    commandRequire apt-get
    for package in "${managedPackages[@]}"; do managed["$package"]=1; done
    mapfile -t manualPackages < <(apt-mark showmanual 2>/dev/null || true)
    for package in "${manualPackages[@]}"; do manual["$package"]=1; done
    mapfile -t candidates < <(apt-get -s upgrade 2>/dev/null | awk '/^Inst / {print $2}' || true)
    printf '\nApt update candidates\n'
    if ((${#candidates[@]} == 0)); then
        printf '  none found using current metadata\n'
        return 0
    fi
    for package in "${candidates[@]}"; do
        if [[ -n "${managed[$package]:-}" ]]; then
            category=managed
        elif [[ -n "${manual[$package]:-}" ]]; then
            category=unmanaged
        else
            category=system
        fi
        printf '  %-10s %s\n' "$category" "$package"
    done
}

packagesFlatpakUpdatesReport() {
    local -a candidates=()
    local package category managedPackage
    command -v flatpak >/dev/null 2>&1 || { printf '\nFlatpak update candidates\n  flatpak is not installed yet\n'; return 0; }
    mapfile -t candidates < <(flatpak remote-ls --system --updates --columns=application 2>/dev/null || true)
    printf '\nFlatpak update candidates\n'
    if ((${#candidates[@]} == 0)); then
        printf '  none found using current metadata\n'
        return 0
    fi
    for package in "${candidates[@]}"; do
        category=unmanaged
        for managedPackage in "${profileFlatpakPackages[@]}"; do
            [[ "$managedPackage" != "$package" ]] || { category=managed; break; }
        done
        printf '  %-10s %s\n' "$category" "$package"
    done
packagesManagerRequire() {
    case "$1" in
        apt) commandRequire dpkg-query; commandRequire apt-get ;;
        flatpak) commandRequire flatpak ;;
        snap) commandRequire snap ;;
        *) logError "unsupported package manager: $1"; return 2 ;;
    esac
}

packagesPackageInstall() {
    local manager="$1" package="$2"
    case "$manager" in
        apt) changeRun "install apt package: $package" sudo apt-get install -y "$package" ;;
        flatpak) changeRun "install flatpak package: $package" flatpak install --user --noninteractive flathub "$package" ;;
        snap) changeRun "install snap package: $package" sudo snap install "$package" ;;
        *) logError "unsupported package manager: $manager"; return 2 ;;
    esac
}

packagesPackageInstalled() {
    local manager="$1" package="$2"
    case "$manager" in
        apt) dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed' ;;
        flatpak) flatpak info --user "$package" >/dev/null 2>&1 ;;
        snap) snap list "$package" >/dev/null 2>&1 ;;
        *) logError "unsupported package manager: $manager"; return 2 ;;
    esac
}
