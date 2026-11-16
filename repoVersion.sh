#!/usr/bin/env bash
# repoVersion.sh: the version of this repository checkout, for tool headers.
#
# SOURCE this file, then call repoVersionDescribe:
#   source "<repository root>/repoVersion.sh"
#   echo "myTool $(repoVersionDescribe)"
#
# Prints the git description of the checkout against its version tags:
#   v1.4a2                        exactly the commit tagged v1.4a2
#   v1.4a2-4-g1a2b3c4             4 commits after v1.4a2, VERSION unchanged
#   v1.4a2-dirty                  v1.4a2 with uncommitted changes
#   1.4a3 (v1.4a2-1-g1a2b3c4)     a branch numbered 1.4a3, after v1.4a2
# Before the first tag it prints the VERSION file with the commit, and without
# git it prints the VERSION file alone. See .github/additional-instructions.md
# ("Versioning and releases").

_repoVersionRoot="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The version a "git describe" string counts from: v1.4a2-4-g1a2b3c4 -> 1.4a2.
_repoVersionTagOf() {
    local tag="${1#v}"
    printf '%s' "${tag%-*-g*}"
}

repoVersionDescribe() {
    local fileVersion=unknown described
    [[ -f "$_repoVersionRoot/VERSION" ]] && fileVersion="$(tr -d '[:space:]' <"$_repoVersionRoot/VERSION")"
    if ! described="$(git -C "$_repoVersionRoot" describe --tags --match 'v[0-9]*' --dirty --always 2>/dev/null)"; then
        printf '%s' "$fileVersion"
        return 0
    fi
    # Away from a tag, a branch's own VERSION names the work being run.
    local tagged="${described%-dirty}"
    if [[ "$described" == v[0-9]* && ( "$tagged" != *-g[0-9a-f]* || "$(_repoVersionTagOf "$tagged")" == "$fileVersion" ) ]]; then
        printf '%s' "$described"
    elif [[ "$described" == v[0-9]* ]]; then
        printf '%s (%s)' "$fileVersion" "$described"
    else
        printf '%s (%s)' "$fileVersion" "$described"
    fi
}
