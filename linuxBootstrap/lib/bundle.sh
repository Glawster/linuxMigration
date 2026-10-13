#!/usr/bin/env bash

bundleDistributionDetect() {
    local osRelease="${BUNDLE_OS_RELEASE:-/etc/os-release}"
    [[ -r "$osRelease" ]] || { logError "cannot read target OS metadata: $osRelease"; return 2; }
    # shellcheck disable=SC1090
    source "$osRelease"
    printf '%s\n' "${ID:-unknown}"
}

bundleReleaseDetect() {
    local osRelease="${BUNDLE_OS_RELEASE:-/etc/os-release}"
    [[ -r "$osRelease" ]] || { logError "cannot read target OS metadata: $osRelease"; return 2; }
    # shellcheck disable=SC1090
    source "$osRelease"
    printf '%s\n' "${VERSION_ID:-unknown}"
}

bundleArchitectureDetect() {
    dpkg --print-architecture
}

bundlePackagesUnique() {
    printf '%s\n' "$@" | awk 'NF && !seen[$0]++'
}

bundlePlan() {
    local output="$1" distribution="$2" release="$3" architecture="$4" package
    shift 4
    local -a packages=("$@")

    [[ -n "$output" ]] || { logError "bundle requires --output PATH"; return 2; }
    [[ "$output" != / ]] || { logError "bundle output must not be /"; return 2; }
    [[ -n "$distribution" ]] || distribution="$(bundleDistributionDetect)"
    [[ -n "$release" ]] || release="$(bundleReleaseDetect)"
    [[ -n "$architecture" ]] || architecture="$(bundleArchitectureDetect)"

    printf 'Bundle plan\n'
    printf '  Profiles ........ %s\n' "$(IFS=', '; echo "${loadedProfiles[*]}")"
    printf '  Distribution .... %s\n' "$distribution"
    printf '  Release ......... %s\n' "$release"
    printf '  Architecture .... %s\n' "$architecture"
    printf '  Output .......... %s\n' "$output"
    printf '  APT packages ....\n'
    while IFS= read -r package; do
        [[ -n "$package" ]] && printf '    %s\n' "$package"
    done < <(bundlePackagesUnique "${packages[@]}")
    printf '  Action .......... preview only; no files or packages downloaded\n'
}
