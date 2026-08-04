#!/usr/bin/env bash

managedFilesApply() {
    local entry source destination
    for entry in "$@"; do
        [[ "$entry" == *"|"* ]] || {
            logError "managed file requires source|destination: $entry"
            return 2
        }
        source="${entry%%|*}"
        destination="${entry#*|}"
        _managedFilePathValidate "$source" source || return 2
        _managedFilePathValidate "$destination" destination || return 2
        source="$projectDir/configs/$source"
        destination="$HOME/$destination"
        [[ -f "$source" ]] || { logError "managed file source not found: $source"; return 2; }

        if [[ -f "$destination" ]] && cmp -s "$source" "$destination"; then
            itemSkip "managed file already configured: $destination"
        else
            changeRun "configure managed file: $destination" _managedFileInstall "$source" "$destination"
        fi
    done
}

vscodeExtensionsApply() {
    (($#)) || return 0
    commandRequire code
    local extension installed
    installed="$(code --list-extensions 2>/dev/null)"
    for extension in "$@"; do
        [[ "$extension" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*\.[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || {
            logError "invalid VS Code extension identifier: $extension"
            return 2
        }
        if grep -Fxiq "$extension" <<< "$installed"; then
            itemSkip "VS Code extension already installed: $extension"
        else
            changeRun "install VS Code extension: $extension" code --install-extension "$extension"
        fi
    done
}

_managedFileInstall() {
    local source="$1" destination="$2"
    mkdir -p "$(dirname "$destination")"
    install -m 644 "$source" "$destination"
}

_managedFilePathValidate() {
    local path="$1" label="$2"
    if [[ -z "$path" || "$path" == /* || "$path" == *".."* || "$path" == *"|"* ]]; then
        logError "managed file $label must be a safe relative path: $path"
        return 2
    fi
}
