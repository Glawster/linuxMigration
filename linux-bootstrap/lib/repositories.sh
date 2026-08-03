#!/usr/bin/env bash

repositoriesApply() {
    local repository
    for repository in "$@"; do
        logWarning "repository '$repository' has no definition yet; skipping"
    done
}
