#!/usr/bin/env bash

packagesApply() {
    local manager="$1"
    shift
    [[ "$manager" == apt ]] || { logError "unsupported package manager: $manager"; return 2; }
    (($#)) || return 0
    commandRequire dpkg-query
    local package
    for package in "$@"; do
        if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
            itemSkip "apt package already installed: $package"
        else
            changeRun "install apt package: $package" sudo apt-get install -y "$package"
        fi
    done
}

packagesUnsupportedReport() {
    ((${#profileFlatpakPackages[@]} == 0)) || logWarning "Flatpak packages are declared but support is planned: ${profileFlatpakPackages[*]}"
    ((${#profileSnapPackages[@]} == 0)) || logWarning "Snap packages are declared but support is planned: ${profileSnapPackages[*]}"
}
