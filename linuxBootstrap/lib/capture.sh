#!/usr/bin/env bash

captureGitProfile() {
    local profile="$1" target name email defaultBranch temporary
    commandRequire git
    target="$(profileResolve "$profile")"
    name="$(git config --global --get user.name 2>/dev/null || true)"
    email="$(git config --global --get user.email 2>/dev/null || true)"
    defaultBranch="$(git config --global --get init.defaultBranch 2>/dev/null || true)"

    [[ -n "$name$email$defaultBranch" ]] || {
        logError "no supported global Git settings were found to capture"
        return 2
    }
    captureGitValueValidate name "$name"
    captureGitValueValidate email "$email"
    captureGitValueValidate defaultBranch "$defaultBranch"

    [[ -z "$name" ]] || logInfo "captured Git user.name: $name"
    [[ -z "$email" ]] || logInfo "captured Git user.email: $email"
    [[ -z "$defaultBranch" ]] || logInfo "captured Git init.defaultBranch: $defaultBranch"

    temporary="$(mktemp)"
    captureGitProfileRender "$target" "$temporary" "$name" "$email" "$defaultBranch"
    if cmp -s "$target" "$temporary"; then
        rm -f "$temporary"
        itemSkip "Git configuration already captured in profile: $profile"
        return 0
    fi
    changeRun "capture global Git configuration in profile: $profile" \
        captureGitProfileInstall "$temporary" "$target"
    if [[ -e "$temporary" ]]; then
        rm -f "$temporary"
    fi
}

captureGitProfileInstall() {
    local source="$1" target="$2"
    install -m 644 "$source" "$target"
    rm -f "$source"
}

captureGitProfileRender() {
    local source="$1" output="$2" name="$3" email="$4" defaultBranch="$5"
    awk -v name="$name" -v email="$email" -v defaultBranch="$defaultBranch" '
        function printGit() {
            print "git:"
            if (name != "") print "  name: " name
            if (email != "") print "  email: " email
            if (defaultBranch != "") print "  defaultBranch: " defaultBranch
        }
        /^git:[[:space:]]*$/ {
            if (!written) printGit()
            written=1
            inGit=1
            next
        }
        inGit && /^[^[:space:]]/ { inGit=0 }
        inGit { next }
        { print }
        END {
            if (!written) {
                if (NR > 0) print ""
                printGit()
            }
        }
    ' "$source" > "$output"
}

captureGitValueValidate() {
    local key="$1" value="$2"
    [[ -z "$value" ]] && return 0
    [[ "$value" != *$'\n'* && "$value" != *$'\r'* && "$value" != *$'\t'* ]] || {
        logError "Git $key contains unsupported control characters"
        return 2
    }
    [[ "$value" != *': '* && "$value" != *' #'* ]] || {
        logError "Git $key cannot be represented safely in the profile YAML"
        return 2
    }
}
