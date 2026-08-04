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
requestedCommand="install"
requestedProfileAction=""
requestedProfileName=""
dryRun=1
verbose=0

usage() {
    cat <<'EOF'
Usage: bootstrap.sh <command> [options]

Configure a Pop!_OS machine from one or more composable profiles.
Changes are previewed unless --confirm is supplied.

Commands:
  install              Converge packages and configuration (default for legacy syntax)
  update               Converge, then update installed apt and Flatpak packages
  status               Inspect profile compliance without making changes
  profile list         List role and host profiles
  profile show NAME    Show a profile's merged configuration
  profile validate     Validate all profile definitions
  profile add NAME     Preview creation of a new role profile

Options:
  --profile NAME       Load a role or host profile (repeatable)
  --hostname NAME      Override the configured hostname
  --static-ip CIDR     Override the configured static IPv4 address
  -y, --confirm        Apply changes
  --verbose            Show additional diagnostic information
  -h, --help           Show this help
EOF
}

argumentsParse() {
    if (($#)) && [[ "$1" != -* ]]; then
        requestedCommand="$1"
        shift
        if [[ "$requestedCommand" == profile ]]; then
            (($#)) || { logError "profile requires an action"; usage >&2; exit 2; }
            requestedProfileAction="$1"
            shift
            case "$requestedProfileAction" in
                show|add)
                    (($#)) || { logError "profile $requestedProfileAction requires a name"; exit 2; }
                    requestedProfileName="$1"
                    shift
                    ;;
                list|validate) ;;
                *) logError "unknown profile action: $requestedProfileAction"; exit 2 ;;
            esac
        fi
    else
        requestedCommand="install"
    fi
    case "$requestedCommand" in
        install|update|status|profile) ;;
        capture) logError "capture is planned but not implemented yet"; exit 2 ;;
        *) logError "unknown command: $requestedCommand"; usage >&2; exit 2 ;;
    esac
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
            -y|--confirm) dryRun=0; shift ;;
            --verbose) verbose=1; shift ;;
            -h|--help) usage; exit 0 ;;
            *) logError "unknown argument: $1"; usage >&2; exit 2 ;;
        esac
    done
    if [[ "$requestedCommand" != profile ]]; then
        ((${#requestedProfiles[@]})) || requestedProfiles=(common)
    fi
    [[ "$requestedCommand" != status ]] || dryRun=1
    export dryRun verbose
}

modulesLoad() {
    local module
    for module in packages git ssh hostname networking repositories; do
        # shellcheck source=/dev/null
        source "$projectDir/lib/$module.sh"
    done
}

configurationApply() {
    hostnameApply "${requestedHostname:-${profileHostname:-}}"
    networkingApply "${requestedStaticIp:-${profileStaticIp:-}}"
    networkingExpectedValidate "${profileExpectedIp:-}"
    packagesApply apt "${profileAptPackages[@]}"
    packagesApply flatpak "${profileFlatpakPackages[@]}"
    packagesUnsupportedReport
    servicesApply "${profileServices[@]}"
    gitApply
    sshApply
    repositoriesApply "${profileRepositories[@]}"
}

installRun() {
    profilesLoad "${requestedProfiles[@]}"
    configurationApply
    summaryPrint
}

profileRun() {
    case "$requestedProfileAction" in
        list) profilesList ;;
        show) profileShow "$requestedProfileName" ;;
        validate) profilesValidate ;;
        add) profileAdd "$requestedProfileName" ;;
    esac
}

statusRun() {
    profilesLoad "${requestedProfiles[@]}"
    configurationApply
    summaryPrint
}

updateRun() {
    profilesLoad "${requestedProfiles[@]}"
    configurationApply
    packagesUpdate "${profileAptPackages[@]}"
    summaryPrint
}

bootstrapRun() {
    loggingInitialize
    argumentsParse "$@"
    trap 'errorTrap $? "$LINENO" "$BASH_COMMAND"' ERR
    modulesLoad

    logInfo "linux-bootstrap $requestedCommand starting"
    [[ "$dryRun" == 1 && "$requestedCommand" != status && "$requestedCommand" != profile ]] && logWarning "dry-run mode: no system changes will be made"
    case "$requestedCommand" in
        install) installRun ;;
        update) updateRun ;;
        status) statusRun ;;
        profile) profileRun ;;
    esac
}

bootstrapRun "$@"
