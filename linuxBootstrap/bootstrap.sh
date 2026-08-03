#!/usr/bin/env bash
set -Eeuo pipefail

projectDir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export projectDir

# shellcheck source=lib/logging.sh
source "$projectDir/lib/logging.sh"
# shellcheck source=lib/common.sh
source "$projectDir/lib/common.sh"
# shellcheck source=lib/profiles.sh
source "$projectDir/lib/profiles.sh"

declare -a requestedProfiles=()
requestedHostname=""
requestedStaticIp=""
dryRun=1
verbose=0

usage() {
    cat <<'EOF'
Usage: bootstrap.sh [options]

Configure a Pop!_OS machine from one or more composable profiles.
Changes are previewed unless --confirm is supplied.

Options:
  --profile NAME       Load a role or host profile (repeatable)
  --hostname NAME      Override the configured hostname
  --static-ip CIDR     Override the configured static IPv4 address
  --dry-run            Preview changes (the default)
  -y, --confirm        Apply changes
  --verbose            Show additional diagnostic information
  -h, --help           Show this help
EOF
}

argumentsParse() {
    while (($#)); do
        case "$1" in
            --profile)
                argumentRequireValue "$1" "${2:-}"
                requestedProfiles+=("$2")
                shift 2
                ;;
            --hostname)
                argumentRequireValue "$1" "${2:-}"
                requestedHostname="$2"
                shift 2
                ;;
            --static-ip)
                argumentRequireValue "$1" "${2:-}"
                requestedStaticIp="$2"
                shift 2
                ;;
            --dry-run) dryRun=1; shift ;;
            -y|--confirm) dryRun=0; shift ;;
            --verbose) verbose=1; shift ;;
            -h|--help) usage; exit 0 ;;
            *) logError "unknown argument: $1"; usage >&2; exit 2 ;;
        esac
    done
    ((${#requestedProfiles[@]})) || requestedProfiles=(common)
    export dryRun verbose
}

modulesLoad() {
    local module
    for module in packages git ssh hostname networking repositories; do
        # shellcheck source=/dev/null
        source "$projectDir/lib/$module.sh"
    done
}

bootstrapRun() {
    argumentsParse "$@"
    trap 'errorTrap $? "$LINENO" "$BASH_COMMAND"' ERR
    modulesLoad

    logInfo "linux-bootstrap starting"
    [[ -n "$dryRun" ]] && logWarning "dry-run mode: no system changes will be made"
    profilesLoad "${requestedProfiles[@]}"

    hostnameApply "${requestedHostname:-${profileHostname:-}}"
    networkingApply "${requestedStaticIp:-${profileStaticIp:-}}"
    packagesApply apt "${profileAptPackages[@]}"
    packagesUnsupportedReport
    servicesApply "${profileServices[@]}"
    gitApply
    sshApply
    repositoriesApply "${profileRepositories[@]}"
    summaryPrint
}

bootstrapRun "$@"
