#!/usr/bin/env bash

bundleDistributionDetect() {
    local osRelease="${BUNDLE_OS_RELEASE:-/etc/os-release}" ID=""
    [[ -r "$osRelease" ]] || { logError "cannot read target OS metadata: $osRelease"; return 2; }
    # shellcheck disable=SC1090
    source "$osRelease"
    printf '%s\n' "${ID:-unknown}"
}

bundleReleaseDetect() {
    local osRelease="${BUNDLE_OS_RELEASE:-/etc/os-release}" VERSION_ID=""
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

bundleTargetValidate() {
    local distribution="$1" release="$2" architecture="$3"
    local currentDistribution currentRelease currentArchitecture
    currentDistribution="$(bundleDistributionDetect)"
    currentRelease="$(bundleReleaseDetect)"
    currentArchitecture="$(bundleArchitectureDetect)"

    [[ "$distribution" == "$currentDistribution" ]] || {
        logError "bundle creation requires a matching build distribution: target=$distribution current=$currentDistribution"
        return 2
    }
    [[ "$release" == "$currentRelease" ]] || {
        logError "bundle creation requires a matching build release: target=$release current=$currentRelease"
        return 2
    }
    [[ "$architecture" == "$currentArchitecture" ]] || {
        logError "bundle creation requires a matching build architecture: target=$architecture current=$currentArchitecture"
        return 2
    }
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
    printf '  Profiles ........ %s\n' "$(IFS=,; echo "${loadedProfiles[*]}")"
    printf '  Distribution .... %s\n' "$distribution"
    printf '  Release ......... %s\n' "$release"
    printf '  Architecture .... %s\n' "$architecture"
    printf '  Output .......... %s\n' "$output"
    printf '  APT packages ....\n'
    while IFS= read -r package; do
        [[ -n "$package" ]] && printf '    %s\n' "$package"
    done < <(bundlePackagesUnique "${packages[@]}")
    if [[ "$dryRun" == 1 ]]; then
        printf '  Action .......... preview only; no files or packages downloaded\n'
    else
        printf '  Action .......... create offline bootstrap bundle\n'
    fi
}

bundleSourceCopy() {
    local destination="$1"
    mkdir -p "$destination"
    tar -C "$projectDir" \
        --exclude='./.git' \
        --exclude='./build' \
        --exclude='./logs' \
        -cf - . | tar -C "$destination" -xf -
}

bundlePackagesDownload() {
    local destination="$1" package
    shift
    local -a packages=("$@")

    mkdir -p "$destination"
    while IFS= read -r package; do
        [[ -n "$package" ]] || continue
        (
            cd "$destination"
            apt-get download "$package"
        )
    done < <(bundlePackagesUnique "${packages[@]}")
}

bundleRepositoryIndex() {
    local destination="$1"
    command -v dpkg-scanpackages >/dev/null 2>&1 || {
        logError "dpkg-scanpackages is required to create an offline bundle; install dpkg-dev"
        return 2
    }
    (
        cd "$destination"
        dpkg-scanpackages . /dev/null > Packages
        gzip -n -9 -c Packages > Packages.gz
    )
}

bundleManifestWrite() {
    local destination="$1" distribution="$2" release="$3" architecture="$4"
    local profiles packages
    shift 4
    local -a packageList=("$@")
    profiles="$(IFS=,; echo "${loadedProfiles[*]}")"
    packages="$(bundlePackagesUnique "${packageList[@]}" | paste -sd, -)"

    cat > "$destination/manifest.txt" <<EOF
format=1
profiles=$profiles
distribution=$distribution
release=$release
architecture=$architecture
packages=$packages
EOF
}

bundleChecksumsWrite() {
    local destination="$1"
    (
        cd "$destination"
        find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
    )
}

bundleCreate() {
    local output="$1" distribution="$2" release="$3" architecture="$4"
    shift 4
    local -a packages=("$@")
    local bundleRoot="$output/linuxBootstrapBundle"

    bundleTargetValidate "$distribution" "$release" "$architecture"
    [[ ! -e "$output" ]] || {
        logError "bundle output already exists: $output"
        return 2
    }

    mkdir -p "$bundleRoot/packages"
    bundleSourceCopy "$bundleRoot/linuxBootstrap"
    bundlePackagesDownload "$bundleRoot/packages" "${packages[@]}"
    bundleRepositoryIndex "$bundleRoot/packages"
    bundleManifestWrite "$bundleRoot" "$distribution" "$release" "$architecture" "${packages[@]}"
    bundleChecksumsWrite "$bundleRoot"
    logSuccess "offline bootstrap bundle created: $bundleRoot"
}

bundleRunAction() {
    local output="$1" distribution="$2" release="$3" architecture="$4"
    shift 4
    local -a packages=("$@")

    [[ -n "$distribution" ]] || distribution="$(bundleDistributionDetect)"
    [[ -n "$release" ]] || release="$(bundleReleaseDetect)"
    [[ -n "$architecture" ]] || architecture="$(bundleArchitectureDetect)"
    bundlePlan "$output" "$distribution" "$release" "$architecture" "${packages[@]}"
    [[ "$dryRun" == 1 ]] || bundleCreate "$output" "$distribution" "$release" "$architecture" "${packages[@]}"
}
