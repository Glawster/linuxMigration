#!/usr/bin/env bash
# repoVersion.sh: the version of this repository checkout, for tool headers.
#
# SOURCE this file, then call repoVersionDescribe:
#   source "<repository root>/repoVersion.sh"
#   echo "myTool $(repoVersionDescribe)"
#
# Prints the git description of the checkout against its release tags:
#   v1.3                  exactly the v1.3 release
#   v1.3-4-g1a2b3c4       4 commits after v1.3
#   v1.3-dirty            v1.3 with uncommitted changes
# Before the first tag it prints the VERSION file with the commit, and without
# git it prints the VERSION file alone. See .github/additional-instructions.md
# ("Versioning and releases").

_repoVersionRoot="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

repoVersionDescribe() {
    local fileVersion=unknown described
    [[ -f "$_repoVersionRoot/VERSION" ]] && fileVersion="$(tr -d '[:space:]' <"$_repoVersionRoot/VERSION")"
    if ! described="$(git -C "$_repoVersionRoot" describe --tags --match 'v[0-9]*' --dirty --always 2>/dev/null)"; then
        printf '%s' "$fileVersion"
        return 0
    fi
    if [[ "$described" == v[0-9]* ]]; then
        printf '%s' "$described"
    else
        printf '%s (%s)' "$fileVersion" "$described"
    fi
}
