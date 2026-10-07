#!/usr/bin/env bash

_wowBooleanValidate() {
    [[ "$1" == true || "$1" == false ]] || {
        logError "WoW: enabled must be true or false (got: $1)"
        return 2
    }
}

_wowDriveApply() {
    local prefix="$1" gamesDir="$2" drive="$prefix/dosdevices/g:"
    mkdir -p "$prefix/dosdevices"
    [[ ! -e "$drive" || -L "$drive" ]] || {
        logError "WoW: cannot manage Wine drive G: because $drive is not a symbolic link"
        return 1
    }
    ln -sfn "$gamesDir" "$drive"
}

_wowDriveMatches() {
    local drive="$1/dosdevices/g:"
    [[ -L "$drive" && "$(readlink "$drive")" == "$2" ]]
}

_wowInstallerDownload() {
    local target="$1"
    mkdir -p "$(dirname "$target")"
    curl -fL 'https://downloader.battle.net/download/getInstaller?os=win&installer=Battle.net-Setup.exe' -o "$target"
}

_wowInstallerRun() {
    local installer="$1" prefix="$2" installDir="$3" protonPath="$4"
    logWarning "WoW: Battle.net setup is interactive; install World of Warcraft to G:\\$(basename "$installDir")"
    WINEPREFIX="$prefix" GAMEID=umu-default STORE=battlenet PROTONPATH="$protonPath" \
        STEAM_COMPAT_LIBRARY_PATHS="$(dirname "$installDir")" umu-run "$installer"
    _wowBattleNetFind "$prefix" >/dev/null || {
        logError "WoW: Battle.net setup exited without installing the launcher"
        return 1
    }
}

_wowBattleNetFind() {
    local prefix="$1" candidate
    for candidate in \
        "$prefix/drive_c/Program Files (x86)/Battle.net/Battle.net Launcher.exe" \
        "$prefix/drive_c/Program Files/Battle.net/Battle.net Launcher.exe"; do
        [[ -f "$candidate" ]] && { printf '%s\n' "$candidate"; return; }
    done
    return 1
}

_wowExecutableFind() {
    local installDir="$1" candidate
    for candidate in "$installDir/_retail_/Wow.exe" "$installDir/World of Warcraft/_retail_/Wow.exe"; do
        [[ -f "$candidate" ]] && { printf '%s\n' "$candidate"; return; }
    done
    return 1
}

_wowLauncherRender() {
    local target="$1" prefix="$2" protonPath="$3" executable="$4" gamesDir="$5"
    mkdir -p "$(dirname "$target")"
    printf '%s\n' \
        '#!/usr/bin/env bash' \
        'set -Eeuo pipefail' \
        'export PATH="$HOME/.local/bin:$PATH"' \
        "export WINEPREFIX=$(printf '%q' "$prefix")" \
        'export GAMEID=umu-default' \
        'export STORE=battlenet' \
        "export PROTONPATH=$(printf '%q' "$protonPath")" \
        "export STEAM_COMPAT_LIBRARY_PATHS=$(printf '%q' "$gamesDir")" \
        'export BATTLE_NET_DISABLE_BROWSER=1' \
        "exec umu-run $(printf '%q' "$executable") \"\$@\"" > "$target"
    chmod 755 "$target"
}

_wowStatus() {
    local installDir="$1" prefix="$2" launcher="$3" compatibilityDir="$4" gamesDir protonPath
    gamesDir="$(dirname "$installDir")"
    logInfo "WoW: enabled by profile"
    command -v umu-run >/dev/null 2>&1 && logInfo "WoW: UMU runner available" || logWarning "WoW: UMU runner missing"
    protonPath="$(_dcsProtonFind "$compatibilityDir")"
    [[ -n "$protonPath" ]] && logInfo "WoW: GE-Proton runner available at $protonPath" || logWarning "WoW: GE-Proton runner missing"
    [[ -d "$prefix" ]] && logInfo "WoW: prefix exists at $prefix" || logWarning "WoW: prefix missing at $prefix"
    _wowDriveMatches "$prefix" "$gamesDir" && logInfo "WoW: Wine drive G: maps to $gamesDir" || logWarning "WoW: Wine drive G: mapping missing"
    _wowBattleNetFind "$prefix" >/dev/null && logInfo "WoW: Battle.net launcher found" || logWarning "WoW: Battle.net launcher missing"
    _wowExecutableFind "$installDir" >/dev/null && logInfo "WoW: installation found at $installDir" || logWarning "WoW: installation missing at $installDir"
    [[ -x "$launcher" ]] && logInfo "WoW: launcher exists at $launcher" || logWarning "WoW: launcher missing at $launcher"
}

wowApply() {
    local enabled="$1" installDir="$2" dataRoot cacheRoot prefix binDir compatibilityDir protonPath installer battleNet wowExecutable gamesDir
    _wowBooleanValidate "$enabled"
    if [[ "$enabled" != true ]]; then
        [[ "${requestedCommand:-install}" == status ]] && logInfo "WoW: disabled by profile" || logVerbose "WoW: disabled by profile"
        return 0
    fi
    [[ "$installDir" == /* && "$installDir" != / ]] || { logError "WoW: installDir must be an absolute path other than /"; return 2; }
    dataRoot="${XDG_DATA_HOME:-$HOME/.local/share}"
    cacheRoot="${XDG_CACHE_HOME:-$HOME/.cache}"
    prefix="$dataRoot/wow/prefix"
    binDir="$HOME/.local/bin"
    compatibilityDir="$dataRoot/Steam/compatibilitytools.d"
    installer="$cacheRoot/linuxBootstrap/Battle.net-Setup.exe"
    gamesDir="$(dirname "$installDir")"
    export PATH="$binDir:$PATH"
    if [[ "${requestedCommand:-install}" == status ]]; then _wowStatus "$installDir" "$prefix" "$binDir/battlenet" "$compatibilityDir"; return; fi
    logInfo "WoW: checking prerequisites"
    commandRequire curl
    command -v umu-run >/dev/null 2>&1 || changeRun "install WoW compatibility runner (UMU)" _dcsRunnerInstall "$dataRoot/linuxBootstrap/umu" "$binDir"
    protonPath="$(_dcsProtonFind "$compatibilityDir")"
    if [[ -z "$protonPath" ]]; then
        changeRun "install latest GE-Proton runner for WoW" _dcsProtonInstall "$compatibilityDir"
        [[ "${dryRun:-1}" == 1 ]] && protonPath="$compatibilityDir/GE-Proton-latest" || protonPath="$(_dcsProtonFind "$compatibilityDir")"
    fi
    [[ -d "$installDir" ]] || changeRun "create WoW installation directory: $installDir" mkdir -p "$installDir"
    [[ -d "$prefix" ]] || changeRun "create WoW prefix directory: $prefix" mkdir -p "$prefix"
    _wowDriveMatches "$prefix" "$gamesDir" || changeRun "map WoW Wine drive G: to $gamesDir" _wowDriveApply "$prefix" "$gamesDir"
    battleNet="$(_wowBattleNetFind "$prefix" 2>/dev/null || true)"
    if [[ -z "$battleNet" ]]; then
        [[ -f "$installer" ]] || changeRun "download official Battle.net installer" _wowInstallerDownload "$installer"
        changeRun "run Battle.net installer for WoW (interactive)" _wowInstallerRun "$installer" "$prefix" "$installDir" "$protonPath"
        [[ "${dryRun:-1}" == 0 ]] && battleNet="$(_wowBattleNetFind "$prefix")" || battleNet="$prefix/drive_c/Program Files (x86)/Battle.net/Battle.net Launcher.exe"
    fi
    [[ -x "$binDir/battlenet" ]] || changeRun "create Battle.net launcher" _wowLauncherRender "$binDir/battlenet" "$prefix" "$protonPath" "$battleNet" "$gamesDir"
    wowExecutable="$(_wowExecutableFind "$installDir" 2>/dev/null || true)"
    [[ -z "$wowExecutable" || -x "$binDir/wow" ]] || changeRun "create World of Warcraft launcher" _wowLauncherRender "$binDir/wow" "$prefix" "$protonPath" "$wowExecutable" "$gamesDir"
    [[ -n "$wowExecutable" ]] || logWarning "WoW: install World of Warcraft from Battle.net and choose G:\\$(basename "$installDir")"
}
