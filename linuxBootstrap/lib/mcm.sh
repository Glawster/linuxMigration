#!/usr/bin/env bash

mcmApply() {
    local enabled="$1" prefix="$2"
    shift 2
    [[ "${enabled,,}" == true ]] || { logVerbose "Media Center Master: disabled by profile"; return; }
    prefix="${prefix/#\~/$HOME}"
    logInfo "Media Center Master: enabled by profile"
    if [[ "${dryRun:-1}" != 1 ]]; then
        commandRequire wine
        commandRequire winetricks
        commandRequire unzip
    fi
    _mcmPrefixApply "$prefix"
    _mcmRuntimeApply "$prefix"
    _mcmDrivesApply "$prefix" "$@"
    _mcmApplicationApply "$prefix"
    _mcmLauncherApply "$prefix"
}

_mcmApplicationApply() {
    local prefix="$1"
    if _mcmExecutableFind "$prefix" >/dev/null; then
        itemSkip "Media Center Master: application installed"
    else
        changeRun "download and run the official Media Center Master installer" _mcmApplicationInstall "$prefix"
    fi
}

_mcmApplicationInstall() {
    local prefix="$1" temporary archive installer
    temporary="$(mktemp -d)"
    archive="$temporary/mcm-setup.zip"
    curl -fsSL https://www.mediacentermaster.com/download/ -o "$archive"
    unzip -tq "$archive" >/dev/null
    unzip -q "$archive" -d "$temporary/setup"
    installer="$(find "$temporary/setup" -type f -iname '*setup.exe' -print -quit)"
    [[ -n "$installer" ]] || { rm -rf -- "$temporary"; logError "Media Center Master setup executable was not found"; return 1; }
    WINEPREFIX="$prefix" WINEDEBUG=-all wine "$installer"
    rm -rf -- "$temporary"
}

_mcmDriveApply() {
    local prefix="$1" specification="$2" letter path target
    IFS='|' read -r letter path <<< "$specification"
    letter="${letter,,}"
    [[ "$letter" =~ ^[d-z]$ && "$path" == /* ]] || { logError "invalid Media Center Master drive mapping: $specification"; return 2; }
    target="$prefix/dosdevices/$letter:"
    if [[ -L "$target" && "$(readlink "$target")" == "$path" ]]; then
        itemSkip "Media Center Master: drive ${letter^^}: already maps to $path"
    else
        changeRun "map Media Center Master drive ${letter^^}: to $path" _mcmDriveLink "$target" "$path"
    fi
}

_mcmDriveLink() {
    local target="$1" path="$2"
    mkdir -p "$(dirname "$target")"
    ln -sfn "$path" "$target"
}

_mcmDrivesApply() {
    local prefix="$1" specification
    shift
    for specification in "$@"; do _mcmDriveApply "$prefix" "$specification"; done
}

_mcmExecutableFind() {
    local prefix="$1" candidate
    for candidate in \
        "$prefix/drive_c/Program Files (x86)/Media Center Master/MCMStubLauncher.exe" \
        "$prefix/drive_c/Program Files/Media Center Master/MCMStubLauncher.exe"; do
        [[ -f "$candidate" ]] && { printf '%s\n' "$candidate"; return; }
    done
    return 1
}

_mcmLauncherApply() {
    local prefix="$1" target="$HOME/.local/bin/media-center-master"
    if [[ -x "$target" ]] && grep -Fq "WINEPREFIX=\"$prefix\"" "$target"; then
        itemSkip "Media Center Master: launcher installed"
    else
        changeRun "install Media Center Master launcher" _mcmLauncherInstall "$prefix" "$target"
    fi
}

_mcmLauncherInstall() {
    local prefix="$1" target="$2"
    mkdir -p "$(dirname "$target")"
    cat > "$target" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
export WINEPREFIX="$prefix"
export WINEDEBUG=-all
executable="\$WINEPREFIX/drive_c/Program Files (x86)/Media Center Master/MCMStubLauncher.exe"
[[ -f "\$executable" ]] || executable="\$WINEPREFIX/drive_c/Program Files/Media Center Master/MCMStubLauncher.exe"
exec wine "\$executable" "\$@"
EOF
    chmod 755 "$target"
}

_mcmPrefixApply() {
    local prefix="$1"
    if [[ -d "$prefix/drive_c" ]]; then
        itemSkip "Media Center Master: Wine prefix exists"
    else
        changeRun "create Media Center Master Wine prefix at $prefix" env WINEARCH=win64 WINEPREFIX="$prefix" WINEDEBUG=-all wineboot -u
    fi
}

_mcmRuntimeApply() {
    local prefix="$1"
    if WINEPREFIX="$prefix" WINEDEBUG=-all wine reg query 'HKLM\Software\Microsoft\NET Framework Setup\NDP\v4\Full' /v Release 2>/dev/null | grep -Eq '0x(8[0-9a-f]{4}|[9a-f][0-9a-f]{4,})'; then
        itemSkip "Media Center Master: .NET Framework 4.8 is installed"
    else
        changeRun "install .NET Framework 4.8 and core fonts in the Media Center Master prefix" _mcmRuntimeInstall "$prefix"
    fi
}

_mcmRuntimeInstall() {
    local prefix="$1"
    WINEPREFIX="$prefix" WINEDEBUG=-all winetricks -q dotnet48 corefonts win10
}
