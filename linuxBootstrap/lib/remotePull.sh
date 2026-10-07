#!/usr/bin/env bash
# Copy files from a remote directory with rsync, then remove each source
# file after a successful transfer. Not a bootstrap module; source this
# from standalone scripts that need the same workflow.

applicationName="${applicationName:-pullRemote}"
dest="${dest:-}"
dryRun="${dryRun:-1}"
includeAll="${includeAll:-0}"
includeExts=()
mountPath="${mountPath:-}"
REMOTE="${REMOTE:-}"
REMOTE_DIR="${REMOTE_DIR:-}"
remoteHost="${remoteHost:-}"
remoteUser="${remoteUser:-andy}"
rsyncArgs=()
sourceDir="${sourceDir:-}"

remotePullMain() {
    argsParse "$@"
    loggingInitialize
    log_doing "starting"
    commandRequire rsync
    commandRequire ssh
    destValidate
    remoteDirResolve
    filesPull
    remoteEmptyDirsPrune
    summaryPrint
    log_done "finished"
}

## args

argsParse() {
    local sawExt=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -y|--confirm)
                dryRun=""
                shift
                ;;
            --all)
                includeAll=1
                includeExts=()
                shift
                ;;
            --dest)
                _argumentRequireValue "$1" "${2:-}"
                dest="$2"
                shift 2
                ;;
            --ext)
                _argumentRequireValue "$1" "${2:-}"
                if ((sawExt == 0)); then
                    includeExts=()
                    includeAll=0
                    sawExt=1
                fi
                includeExts+=("$2")
                shift 2
                ;;
            --host)
                _argumentRequireValue "$1" "${2:-}"
                remoteHost="$2"
                shift 2
                ;;
            --mount)
                _argumentRequireValue "$1" "${2:-}"
                mountPath="$2"
                shift 2
                ;;
            --source)
                _argumentRequireValue "$1" "${2:-}"
                sourceDir="$2"
                shift 2
                ;;
            --user)
                _argumentRequireValue "$1" "${2:-}"
                remoteUser="$2"
                shift 2
                ;;
            -h|--help)
                argsUsage
                exit 0
                ;;
            *)
                echo "ERROR: unknown argument: $1" >&2
                argsUsage >&2
                exit 2
                ;;
        esac
    done
    dest="${dest/#\~/$HOME}"
}

argsUsage() {
    local scriptName="${0##*/}"
    cat <<EOF
Usage: ${scriptName} [--confirm] [--source DIR] [--dest DIR] [--ext EXT] [--all]

Copy files from ${remoteUser}@${remoteHost:-HOST}:~/downloads (or
~/Downloads) to ${dest:-DEST}. Preview only unless --confirm is given.
Successfully copied source files are removed on the remote host.
Incomplete downloads (.part, .crdownload) are left in place.

  -y, --confirm   Transfer files and remove remote sources
  --source DIR    Remote source directory
  --dest DIR      Local destination directory
  --host HOST     Remote host
  --user USER     Remote user
  --ext EXT       Include this extension (repeatable; replaces defaults)
  --all           Copy every complete file, not only matching extensions
  --mount PATH    Require this mount before writing
  -h, --help      Show this help
EOF
}

## dest

destValidate() {
    if [[ -z "$dest" ]]; then
        log_error "destination is required"
        exit 1
    fi
    log_value "destination" "$dest"
    if [[ ! -e "$dest" ]]; then
        log_error "destination does not exist: $dest"
        exit 1
    fi
    if [[ ! -d "$dest" ]]; then
        log_error "destination is not a directory: $dest"
        exit 1
    fi
    if [[ ! -w "$dest" ]]; then
        log_error "destination is not writable: $dest"
        exit 1
    fi
    dest="$(cd "$dest" && pwd)"
    if [[ -n "$mountPath" && ( "$dest" == "$mountPath" || "$dest" == "$mountPath"/* ) ]]; then
        if ! findmnt -n "$mountPath" >/dev/null 2>&1 && ! findmnt -n "$dest" >/dev/null 2>&1; then
            log_error "required mount is not mounted: $mountPath"
            exit 1
        fi
    fi
}

## files

filesPull() {
    if ((includeAll == 0)) && [[ ${#includeExts[@]} -eq 0 ]]; then
        log_error "specify --ext or --all"
        exit 2
    fi
    filesRsyncArgsBuild
    log_action "copying files"
    if [[ -z "${dryRun:-}" ]]; then
        rsync "${rsyncArgs[@]}" --remove-source-files "${REMOTE}:${REMOTE_DIR}/" "${dest}/"
        log_done "copying files"
    else
        rsync "${rsyncArgs[@]}" --dry-run "${REMOTE}:${REMOTE_DIR}/" "${dest}/"
    fi
}

filesRsyncArgsBuild() {
    local ext
    rsyncArgs=(
        -avh
        --progress
        --partial
        --ignore-case
        --prune-empty-dirs
    )
    if ((includeAll == 0)); then
        rsyncArgs+=(--include='*/')
        for ext in "${includeExts[@]}"; do
            ext="${ext#.}"
            rsyncArgs+=(--include="*.${ext}")
        done
        rsyncArgs+=(--exclude='*')
    fi
    rsyncArgs+=(
        --exclude='*.part'
        --exclude='*.crdownload'
        --exclude='*.aria2'
        --exclude='*.tmp'
    )
}

## logging

loggingInitialize() {
    local packageDir logUtils
    if [[ -n "${LOG_UTILS:-}" ]]; then
        logUtils="$LOG_UTILS"
    else
        packageDir="$(python3 -c 'import organiseMyProjects, os; print(os.path.dirname(organiseMyProjects.__file__))')" || {
            echo "ERROR: organiseMyProjects is required" >&2
            exit 127
        }
        logUtils="${packageDir}/logUtils.sh"
    fi
    if [[ ! -f "$logUtils" ]]; then
        echo "ERROR: logUtils.sh not found: $logUtils" >&2
        exit 127
    fi
    # shellcheck source=/dev/null
    source "$logUtils"
    setApplication "$applicationName"
}

## remote

remoteDirResolve() {
    if [[ -z "$remoteHost" ]]; then
        log_error "remote host is required"
        exit 1
    fi
    REMOTE="${remoteUser}@${remoteHost}"
    log_doing "resolving remote source directory"
    if [[ -n "$sourceDir" ]]; then
        REMOTE_DIR="$(ssh "$REMOTE" bash -s -- "$sourceDir" <<'EOF'
dir="$1"
if [[ "$dir" == ~* ]]; then
    dir="${dir/#\~/$HOME}"
fi
if [[ -d "$dir" ]]; then
    printf '%s\n' "$dir"
    exit 0
fi
echo "error: remote directory does not exist: $dir" >&2
exit 1
EOF
)"
    else
        REMOTE_DIR="$(ssh "$REMOTE" bash -s <<'EOF'
if [[ -d "$HOME/downloads" ]]; then
    printf '%s\n' "$HOME/downloads"
elif [[ -d "$HOME/Downloads" ]]; then
    printf '%s\n' "$HOME/Downloads"
else
    echo "error: neither ~/downloads nor ~/Downloads exists" >&2
    exit 1
fi
EOF
)"
    fi
    log_value "source" "${REMOTE}:${REMOTE_DIR}"
}

remoteEmptyDirsPrune() {
    [[ -z "${dryRun:-}" ]] || return 0
    log_action "removing empty remote directories"
    ssh "$REMOTE" "find $(printf '%q' "$REMOTE_DIR") -mindepth 1 -type d -empty -delete"
    log_done "removing empty remote directories"
}

## summary

summaryPrint() {
    local mode="dry-run"
    local status="preview complete (pass --confirm to transfer)"
    if [[ -z "${dryRun:-}" ]]; then
        mode="apply"
        status="transfer complete"
    fi
    printf '\nSummary\n'
    printf '  Source ......... %s\n' "${REMOTE}:${REMOTE_DIR}"
    printf '  Destination .... %s\n' "$dest"
    printf '  Mode ........... %s\n' "$mode"
    printf '  Status ......... %s\n' "$status"
}

## utilities

commandRequire() {
    command -v "$1" >/dev/null 2>&1 || {
        log_error "required command not found: $1"
        exit 127
    }
}

_argumentRequireValue() {
    local option="$1" value="$2"
    if [[ -z "$value" || "$value" == --* ]]; then
        echo "ERROR: $option requires a value" >&2
        exit 2
    fi
}
