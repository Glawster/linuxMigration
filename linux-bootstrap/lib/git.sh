#!/usr/bin/env bash

gitApply() {
    ((${#profileGit[@]})) || return 0
    commandRequire git
    local key desired current gitKey
    for key in "${!profileGit[@]}"; do
        desired="${profileGit[$key]}"
        case "$key" in
            name) gitKey=user.name ;;
            email) gitKey=user.email ;;
            defaultBranch) gitKey=init.defaultBranch ;;
            *) logWarning "unsupported Git profile key: $key"; continue ;;
        esac
        current="$(git config --global --get "$gitKey" 2>/dev/null || true)"
        if [[ "$current" == "$desired" ]]; then
            itemSkip "Git setting already configured: $gitKey"
        else
            changeRun "configure Git $gitKey" git config --global "$gitKey" "$desired"
        fi
    done
}
