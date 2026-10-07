#!/usr/bin/env bash

davinciApply() {
    local enabled="$1" remove="$2" installerDir="$3"
    enabled="${enabled,,}"
    remove="${remove,,}"
    installerDir="${installerDir/#\~/$HOME}"
    [[ "$enabled" =~ ^(true|false)$ && "$remove" =~ ^(true|false)$ ]] || { logError "DaVinci Resolve enabled/remove values must be true or false"; return 2; }
    [[ "$enabled" != true || "$remove" != true ]] || { logError "DaVinci Resolve cannot be enabled and removed by the same profile"; return 2; }
    if [[ "$remove" == true ]]; then
        _davinciRemoveApply
    elif [[ "$enabled" == true ]]; then
        _davinciInstallApply "$installerDir"
    else
        logVerbose "DaVinci Resolve: unmanaged by profile"
    fi
}

_davinciGpuValidate() {
    if command -v nvidia-smi >/dev/null 2>&1; then
        itemSkip "DaVinci Resolve: NVIDIA driver available"
    elif [[ "${dryRun:-1}" == 1 ]]; then
        logWarning "DaVinci Resolve: NVIDIA driver was not detected"
    else
        logError "DaVinci Resolve requires the NVIDIA driver on this host"
        return 2
    fi
}

_davinciInstallApply() {
    local installerDir="$1" installer
    _davinciGpuValidate
    if [[ -x /opt/resolve/bin/resolve ]]; then
        itemSkip "DaVinci Resolve: application installed"
    else
        installer="$(_davinciInstallerFind "$installerDir")" || {
            logWarning "DaVinci Resolve: place the Linux .zip or .run installer in $installerDir"
            ((summaryFailed += 1))
            return 1
        }
        changeRun "install DaVinci Resolve from $installer" _davinciInstallerRun "$installer"
    fi
    _davinciLauncherApply
}

_davinciInstallerFind() {
    local installerDir="$1" installer
    [[ -d "$installerDir" ]] || return 1
    installer="$(find "$installerDir" -maxdepth 1 -type f \( \
        -iname 'DaVinci_Resolve*_Linux.zip' -o \
        -iname 'DaVinci_Resolve*_Linux.run' \
    \) -printf '%f\n' | sort -V | tail -n 1)"
    [[ -n "$installer" ]] || return 1
    printf '%s/%s\n' "$installerDir" "$installer"
}

_davinciInstallerRun() {
    local package="$1" temporary="" installer="$package"
    if [[ "$package" == *.zip ]]; then
        temporary="$(mktemp -d)"
        unzip -tq "$package" >/dev/null
        unzip -q "$package" -d "$temporary"
        installer="$(find "$temporary" -type f -iname 'DaVinci_Resolve*_Linux.run' -print -quit)"
        [[ -n "$installer" ]] || { rm -rf -- "$temporary"; logError "DaVinci Resolve .run installer was not found in the archive"; return 1; }
    fi
    chmod u+x "$installer"
    sudo env SKIP_PACKAGE_CHECK=1 "$installer" -i
    [[ -z "$temporary" ]] || rm -rf -- "$temporary"
}

_davinciLauncherApply() {
    local target="$HOME/bin/davinci-resolve"
    if [[ -x "$target" ]] && grep -Fq '/opt/resolve/bin/resolve' "$target"; then
        itemSkip "DaVinci Resolve: launcher installed"
    else
        changeRun "install DaVinci Resolve launcher in ~/bin" _davinciLauncherInstall "$target"
    fi
}

_davinciLauncherInstall() {
    local target="$1"
    mkdir -p "$(dirname "$target")"
    printf '%s\n' '#!/usr/bin/env bash' 'set -Eeuo pipefail' 'exec /opt/resolve/bin/resolve "$@"' > "$target"
    chmod 755 "$target"
}

_davinciRemoveApply() {
    if [[ -x /opt/resolve/installer ]]; then
        changeRun "uninstall DaVinci Resolve from this host" sudo /opt/resolve/installer -u
    elif [[ -e /opt/resolve ]]; then
        logError "DaVinci Resolve exists but its official uninstaller is missing: /opt/resolve/installer"
        ((summaryFailed += 1))
        return 1
    else
        itemSkip "DaVinci Resolve: already absent"
    fi
    if [[ -e "$HOME/bin/davinci-resolve" ]]; then
        changeRun "remove DaVinci Resolve launcher from ~/bin" rm -f -- "$HOME/bin/davinci-resolve"
    else
        itemSkip "DaVinci Resolve: launcher already absent"
    fi
}
