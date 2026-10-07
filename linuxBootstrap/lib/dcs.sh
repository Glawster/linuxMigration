#!/usr/bin/env bash

dcsUmuArchiveSha256="138ce4b8843608a257d4bee88191ca78a989778bcefd8abb3c1d1aaac3ac6fb8"
dcsUmuVersion="1.4.0"

_dcsBooleanValidate() {
    local name="$1" value="$2"
    [[ "$value" == true || "$value" == false ]] || {
        logError "DCS: $name must be true or false (got: $value)"
        return 2
    }
}

_dcsSkip() {
    logInfo "$1"
    ((summarySkipped += 1))
}

_dcsDesktopRender() {
    local target="$1" name="$2" executable="$3" icon="$4"
    mkdir -p "$(dirname "$target")"
    printf '%s\n' \
        '[Desktop Entry]' \
        'Type=Application' \
        "Name=$name" \
        "Exec=$executable" \
        "Icon=$icon" \
        'Terminal=false' \
        'Categories=Game;' > "$target"
    chmod 755 "$target"
}

_dcsInstallerDownload() {
    local target="$1" page url
    page="$(curl -fsSL 'https://www.digitalcombatsimulator.com/en/downloads/world/stable/')"
    url="$(_dcsInstallerUrlRead <<< "$page")"
    [[ -n "$url" ]] || {
        logError "DCS: could not discover DCS_World_Web.exe on the Eagle Dynamics download page"
        return 1
    }
    [[ "$url" == http* ]] || url="https://www.digitalcombatsimulator.com$url"
    mkdir -p "$(dirname "$target")"
    curl -fL "$url" -o "$target"
}

_dcsInstallerUrlRead() {
    sed -nE 's/.*href="([^"]*DCS_World_[Ww]eb\.exe[^"]*)".*/\1/p' | sed -n '1p'
}

_dcsInstallerRun() {
    local installer="$1" prefix="$2" installDir="$3" protonPath="$4"
    logWarning "DCS: the Eagle Dynamics installer is interactive; select G:\\$(basename "$installDir") as its destination"
    WINEPREFIX="$prefix" GAMEID=umu-default STORE=none PROTONPATH="$protonPath" \
        STEAM_COMPAT_LIBRARY_PATHS="$(dirname "$installDir")" umu-run "$installer"
    [[ -f "$installDir/bin/DCS.exe" && -f "$installDir/bin/DCS_updater.exe" ]] || {
        logError "DCS: installer exited without creating the expected DCS installation at $installDir"
        return 1
    }
}

_dcsDriveApply() {
    local prefix="$1" gamesDir="$2" drive="$prefix/dosdevices/g:"
    mkdir -p "$prefix/dosdevices"
    if [[ -e "$drive" && ! -L "$drive" ]]; then
        logError "DCS: cannot manage Wine drive G: because $drive is not a symbolic link"
        return 1
    fi
    ln -sfn "$gamesDir" "$drive"
}

_dcsDriveMatches() {
    local prefix="$1" gamesDir="$2" drive="$prefix/dosdevices/g:"
    [[ -L "$drive" && "$(readlink "$drive")" == "$gamesDir" ]]
}

_dcsLauncherRender() {
    local target="$1" prefix="$2" installDir="$3" protonPath="$4" action="$5" executable arguments=""
    case "$action" in
        launch) executable="$installDir/bin/DCS.exe" ;;
        update) executable="$installDir/bin/DCS_updater.exe" ;;
        repair) executable="$installDir/bin/DCS_updater.exe"; arguments=" repair" ;;
        *) logError "DCS: unsupported launcher action: $action"; return 2 ;;
    esac
    mkdir -p "$(dirname "$target")"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'set -Eeuo pipefail' \
        'export PATH="$HOME/.local/bin:$PATH"' \
        "export WINEPREFIX=$(printf '%q' "$prefix")" \
        'export GAMEID=umu-default' \
        'export STORE=none' \
        "export PROTONPATH=$(printf '%q' "$protonPath")" \
        "export STEAM_COMPAT_LIBRARY_PATHS=$(printf '%q' "$(dirname "$installDir")")" \
        "exec umu-run $(printf '%q' "$executable")$arguments \"\$@\"" > "$target"
    chmod 755 "$target"
}

_dcsLauncherMatches() {
    local target="$1" protonPath="$2"
    [[ -x "$target" ]] && grep -Fqx "export PROTONPATH=$(printf '%q' "$protonPath")" "$target"
}

_dcsProtonFind() {
    local compatibilityDir="$1"
    [[ -d "$compatibilityDir" ]] || return 0
    find "$compatibilityDir" -mindepth 1 -maxdepth 1 -type d -name 'GE-Proton*' -printf '%p\n' 2>/dev/null |
        sort -V | tail -n 1
}

_dcsProtonInstall() {
    local compatibilityDir="$1" metadata tag archive checksum temporary
    metadata="$(curl -fsSL 'https://api.github.com/repos/GloriousEggroll/proton-ge-custom/releases/latest')"
    tag="$(printf '%s\n' "$metadata" | sed -nE 's/^[[:space:]]*"tag_name": "(GE-Proton[0-9-]+)",/\1/p' | sed -n '1p')"
    [[ "$tag" =~ ^GE-Proton[0-9]+-[0-9]+$ ]] || {
        logError "DCS: could not determine the latest GE-Proton release"
        return 1
    }
    archive="$tag.tar.gz"
    checksum="$tag.sha512sum"
    temporary="$(mktemp -d)"
    curl -fsSL "https://github.com/GloriousEggroll/proton-ge-custom/releases/download/$tag/$archive" -o "$temporary/$archive"
    curl -fsSL "https://github.com/GloriousEggroll/proton-ge-custom/releases/download/$tag/$checksum" -o "$temporary/$checksum"
    (cd "$temporary" && sha512sum -c "$checksum") || {
        logError "DCS: GE-Proton archive checksum mismatch"
        rm -rf -- "$temporary"
        return 1
    }
    mkdir -p "$compatibilityDir"
    tar -xzf "$temporary/$archive" -C "$compatibilityDir"
    rm -rf -- "$temporary"
}

_dcsRunnerInstall() {
    local targetDir="$1" binDir="$2"
    local temporary archive url actual
    [[ "$(uname -m)" == x86_64 ]] || {
        logError "DCS: the managed UMU runner currently supports x86_64 only"
        return 2
    }
    [[ "$dcsUmuArchiveSha256" =~ ^[0-9a-f]{64}$ ]] || {
        logError "DCS: invalid pinned UMU archive checksum"
        return 2
    }
    archive="umu-launcher-$dcsUmuVersion-zipapp.tar"
    url="https://github.com/Open-Wine-Components/umu-launcher/releases/download/$dcsUmuVersion/$archive"
    temporary="$(mktemp -d)"
    curl -fsSL "$url" -o "$temporary/$archive"
    actual="$(sha256sum "$temporary/$archive" | awk '{print $1}')"
    if [[ "$actual" != "$dcsUmuArchiveSha256" ]]; then
        logError "DCS: UMU launcher package checksum mismatch"
        rm -rf -- "$temporary"
        return 1
    fi
    tar -xf "$temporary/$archive" -C "$temporary"
    mkdir -p "$targetDir" "$binDir"
    install -m 755 "$temporary/umu/umu-run" "$targetDir/umu-run"
    ln -sfn "$targetDir/umu-run" "$binDir/umu-run"
    rm -rf -- "$temporary"
}

_dcsStatus() {
    local installDir="$1" prefix="$2" launcher="$3" vr="$4" compatibilityDir="$5" protonPath gamesDir
    gamesDir="$(dirname "$installDir")"
    logInfo "DCS: enabled by profile"
    command -v umu-run >/dev/null 2>&1 && logInfo "DCS: compatibility runner available" || logWarning "DCS: compatibility runner missing (umu-run)"
    protonPath="$(_dcsProtonFind "$compatibilityDir")"
    [[ -n "$protonPath" ]] && logInfo "DCS: GE-Proton runner available at $protonPath" || logWarning "DCS: GE-Proton runner missing"
    [[ -d "$prefix" ]] && logInfo "DCS: prefix exists at $prefix" || logWarning "DCS: prefix missing at $prefix"
    _dcsDriveMatches "$prefix" "$gamesDir" && logInfo "DCS: Wine drive G: maps to $gamesDir" || logWarning "DCS: Wine drive G: is not mapped to $gamesDir"
    [[ -f "$installDir/bin/DCS.exe" ]] && logInfo "DCS: installation found at $installDir" || logWarning "DCS: installation missing at $installDir"
    [[ -f "$installDir/bin/DCS_updater.exe" ]] && logInfo "DCS: DCS_updater.exe exists" || logWarning "DCS: DCS_updater.exe missing"
    [[ -x "$launcher" ]] && logInfo "DCS: launcher exists at $launcher" || logWarning "DCS: launcher missing at $launcher"
    if [[ "$vr" == true ]]; then
        command -v steam >/dev/null 2>&1 && logInfo "DCS: VR dependency Steam is available" || logWarning "DCS: VR dependency Steam is missing"
        logInfo "DCS: VR is enabled; verify 2D first, then configure SteamVR/OpenXR manually"
    fi
}

dcsApply() {
    local enabled="$1" installDir="$2" vr="$3"
    local dataRoot cacheRoot prefix binDir applicationsDir umuDir compatibilityDir protonPath installer launcher updater repair
    _dcsBooleanValidate enabled "$enabled"
    _dcsBooleanValidate vr "$vr"
    if [[ "$enabled" != true ]]; then
        if [[ "${requestedCommand:-install}" == status ]]; then
            logInfo "DCS: disabled by profile"
        else
            logVerbose "DCS: disabled by profile"
        fi
        return 0
    fi
    [[ "$installDir" == /* && "$installDir" != / ]] || {
        logError "DCS: installDir must be an absolute path other than /"
        return 2
    }

    dataRoot="${XDG_DATA_HOME:-$HOME/.local/share}"
    cacheRoot="${XDG_CACHE_HOME:-$HOME/.cache}"
    prefix="$dataRoot/dcs/prefix"
    binDir="$HOME/.local/bin"
    export PATH="$binDir:$PATH"
    applicationsDir="$dataRoot/applications"
    umuDir="$dataRoot/linuxBootstrap/umu"
    compatibilityDir="$dataRoot/Steam/compatibilitytools.d"
    installer="$cacheRoot/linuxBootstrap/DCS_World_Web.exe"
    launcher="$binDir/dcs-world"
    updater="$binDir/dcs-updater"
    repair="$binDir/dcs-repair"

    if [[ "${requestedCommand:-install}" == status ]]; then
        _dcsStatus "$installDir" "$prefix" "$launcher" "$vr" "$compatibilityDir"
        return
    fi

    logInfo "DCS: checking prerequisites"
    command -v curl >/dev/null 2>&1 || { logError "DCS: required command not found: curl"; return 127; }
    command -v sha256sum >/dev/null 2>&1 || { logError "DCS: required command not found: sha256sum"; return 127; }
    command -v sha512sum >/dev/null 2>&1 || { logError "DCS: required command not found: sha512sum"; return 127; }
    if command -v umu-run >/dev/null 2>&1; then
        _dcsSkip "DCS: compatibility runner available"
    else
        command -v tar >/dev/null 2>&1 || { logError "DCS: required command not found: tar"; return 127; }
        command -v install >/dev/null 2>&1 || { logError "DCS: required command not found: install"; return 127; }
        changeRun "install DCS compatibility runner (UMU)" _dcsRunnerInstall "$umuDir" "$binDir"
    fi

    protonPath="$(_dcsProtonFind "$compatibilityDir")"
    if [[ -n "$protonPath" ]]; then
        _dcsSkip "DCS: GE-Proton runner available at $protonPath"
    else
        changeRun "install latest GE-Proton runner for DCS" _dcsProtonInstall "$compatibilityDir"
        if [[ "${dryRun:-1}" == 0 ]]; then
            protonPath="$(_dcsProtonFind "$compatibilityDir")"
            [[ -n "$protonPath" ]] || { logError "DCS: GE-Proton installation did not produce a runner"; return 1; }
        else
            protonPath="$compatibilityDir/GE-Proton-latest"
        fi
    fi

    [[ -d "$installDir" ]] || changeRun "create DCS installation directory: $installDir" mkdir -p "$installDir"
    [[ -d "$prefix" ]] || changeRun "create DCS prefix directory: $prefix" mkdir -p "$prefix"
    _dcsDriveMatches "$prefix" "$(dirname "$installDir")" || \
        changeRun "map DCS Wine drive G: to $(dirname "$installDir")" _dcsDriveApply "$prefix" "$(dirname "$installDir")"

    if [[ -f "$installDir/bin/DCS.exe" && -f "$installDir/bin/DCS_updater.exe" ]]; then
        _dcsSkip "DCS: installation found at $installDir"
    else
        [[ -f "$installer" ]] || changeRun "download Eagle Dynamics DCS World web installer" _dcsInstallerDownload "$installer"
        if [[ "${dryRun:-1}" == 1 || -f "$installer" ]]; then
            changeRun "run Eagle Dynamics installer for $installDir (interactive)" \
                _dcsInstallerRun "$installer" "$prefix" "$installDir" "$protonPath"
        fi
    fi

    _dcsLauncherMatches "$launcher" "$protonPath" || changeRun "create DCS launcher: $launcher" _dcsLauncherRender "$launcher" "$prefix" "$installDir" "$protonPath" launch
    _dcsLauncherMatches "$updater" "$protonPath" || changeRun "create DCS updater launcher: $updater" _dcsLauncherRender "$updater" "$prefix" "$installDir" "$protonPath" update
    _dcsLauncherMatches "$repair" "$protonPath" || changeRun "create DCS repair launcher: $repair" _dcsLauncherRender "$repair" "$prefix" "$installDir" "$protonPath" repair
    [[ -x "$applicationsDir/dcs-world.desktop" ]] || changeRun "create DCS desktop launcher" _dcsDesktopRender "$applicationsDir/dcs-world.desktop" "DCS World" "$launcher" "applications-games"

    if [[ "$vr" == true ]]; then
        logInfo "DCS: VR requested; 2D installation remains independent"
        command -v steam >/dev/null 2>&1 || logWarning "DCS: install Steam and SteamVR before configuring the Valve Index/OpenXR"
    fi
}
