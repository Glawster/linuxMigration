#!/usr/bin/env bash
# Rebalance planning for migrateToRaid (requirement 002, ADR 005). A mapping
# with a "rebalance" object moves only whole title folders, chosen so that its
# local disk falls to the target occupancy: titles already on the destination
# first, then the oldest eligible titles. Only ended shows are eligible.
# The plan is recorded on the first confirmed run and fixed until its titles
# have been removed from the source.
# Sourced by lib/raidMigration.sh; not a bootstrap module.

planEmpty=0

# Lists the top-level folders of a destination, NUL-terminated. A destination
# that does not exist yet has none.
_remoteTopLevelScript='
[ -d "$1" ] || exit 0
cd -- "$1" || exit 3
find . -mindepth 1 -maxdepth 1 -type d -printf "%P\0"
'

# Points a rebalance mapping at its recorded plan, if one exists. Used by
# --check and --remove-source, which must never plan afresh.
planLoadRecorded() {
    local name="$1" recorded="$stateDir/$1.plan"
    mapPlanFile[$name]=""
    [[ -f "$recorded" ]] || return 1
    mapPlanFile[$name]="$recorded"
}

# Decides the scope of a rebalance mapping for this run. Reuses the recorded
# plan until its titles have been removed; otherwise plans afresh, recording
# the new plan only on a confirmed run. Sets planEmpty when nothing would move.
planPrepare() {
    local name="$1" prefix="$2" recorded="$stateDir/$1.plan"
    planEmpty=0
    if [[ -f "$recorded" && "$(stateGet sourceRemoved no)" != yes ]]; then
        mapPlanFile[$name]="$recorded"
        _sayField "Plan:" "recorded $(stateGet planCreated unknown): $(stateGet planTitles '?') titles, $(_bytesFormat "$(stateGet planBytes 0)")"
        _sayField "" "(fixed until its titles are removed; delete $recorded to plan again)"
        return 0
    fi
    if [[ "$action" == verify ]]; then
        _mappingFail "$name" "no rebalance plan is recorded; run with --confirm first"
        return 1
    fi
    planBuild "$name" "$prefix" || return 1
    if ((planCount == 0)); then
        planEmpty=1
        return 0
    fi
    if [[ -n "${dryRun:-}" ]]; then
        mapPlanFile[$name]="$prefix.plan"
        return 0
    fi
    # A confirmed run starts a new cycle: the finished one is kept for audit.
    [[ -f "$recorded" ]] && _planArchive "$name"
    cp -f -- "$prefix.plan" "$recorded"
    mapPlanFile[$name]="$recorded"
    stateSave "$name" planCreated="$(date -Is)" planTitles="$planCount" planBytes="$planBytes" \
        planTargetPercent="${mapRebalance[$name]}"
    stateHistoryAppend "$name" planned "titles=$planCount bytes=$planBytes target=${mapRebalance[$name]}%"
}

# Builds <prefix>.plan (NUL-terminated title folders) and reports it. Sets
# planCount and planBytes.
planBuild() {
    local name="$1" prefix="$2" source="${mapSource[$1]}" mount="${mapMount[$1]}" kind="${mapType[$1]}"
    local percent="${mapRebalance[$1]}" record title key status used avail total target remaining
    local forced=0 airingCount=0 airingBytes=0 entry reason
    local -A sizes=() onDest=()
    local titles=() eligible=() split=()
    planCount=0 planBytes=0
    : >"$prefix.plan"
    : >"$prefix.plan.report"

    # Size every top-level title folder from one scan of the whole source.
    if ! manifestSource "$source" "$prefix.planSource" "$name" unfiltered 2>"$prefix.planSource.err"; then
        _mappingFail "$name" "could not read the complete source tree: $(tail -n 1 "$prefix.planSource.err")"
        return 1
    fi
    while IFS= read -r -d '' record; do
        _manifestRecordSplit "$record"
        if [[ "$_path" != */* ]]; then
            [[ "$_type" == d ]] && titles+=("$_path")
            continue
        fi
        [[ "$_type" == f ]] && sizes["${_path%%/*}"]=$((${sizes["${_path%%/*}"]:-0} + _size))
    done <"$prefix.planSource"

    if ! destinationRun "$_remoteTopLevelScript" "${mapDest[$name]}" >"$prefix.destTitles" 2>"$prefix.destTitles.err" </dev/null; then
        _mappingFail "$name" "could not list the destination on $destHost: $(tail -n 1 "$prefix.destTitles.err")"
        return 1
    fi
    while IFS= read -r -d '' title; do
        onDest["$title"]=1
    done <"$prefix.destTitles"

    read -r used avail < <(df -B1 --output=used,avail -- "$mount" 2>/dev/null | tail -n 1)
    if [[ ! "$used" =~ ^[0-9]+$ || ! "$avail" =~ ^[0-9]+$ ]] || ((used + avail == 0)); then
        _mappingFail "$name" "could not determine the disk usage of $mount"
        return 1
    fi
    total=$((used + avail))
    target=$((total * percent / 100))

    # Classify: ended shows and every movie are eligible; airing shows stay.
    for title in "${titles[@]}"; do
        key="$(_planDateKey "$kind" "$source/$title")"
        if [[ "$kind" == tv ]]; then
            status="$(_planXmlValue "$source/$title/series.xml" Status)"
            if [[ "${status,,}" != ended ]]; then
                airingCount=$((airingCount + 1))
                airingBytes=$((airingBytes + ${sizes[$title]:-0}))
                [[ -n "${onDest[$title]:-}" ]] && split+=("$title (${status:-no series.xml})")
                continue
            fi
        fi
        eligible+=("$key"$'\t'"$title")
    done

    # Titles already on the destination are reunited first, whatever their
    # age; then the oldest eligible titles until the disk reaches the target.
    remaining="$used"
    while IFS= read -r -d '' entry; do
        key="${entry%%$'\t'*}"
        title="${entry#*$'\t'}"
        if [[ -n "${onDest[$title]:-}" ]]; then
            reason="already on $destPlace"
            forced=$((forced + 1))
        elif ((remaining > target)); then
            reason="oldest"
        else
            continue
        fi
        _planSelect "$prefix" "$title" "$key" "${sizes[$title]:-0}" "$reason"
        remaining=$((remaining - ${sizes[$title]:-0}))
    done < <(_planSortAlreadyThenOldest onDest "${eligible[@]}")

    _planReport "$name" "$prefix" "$mount" "$used" "$total" "$remaining" "$target" "$forced" \
        "$airingCount" "$airingBytes" "${split[@]}"
}

# Moves a finished cycle's records aside so the next plan starts clean.
_planArchive() {
    local name="$1" stamp kind
    stamp="$(date +%Y%m%d-%H%M%S)"
    for kind in state manifest plan; do
        [[ -f "$stateDir/$name.$kind" ]] && mv -f -- "$stateDir/$name.$kind" "$stateDir/$name.$stamp.$kind"
    done
    stateHistoryAppend "$name" cycleArchived "$stamp"
    stateLoad "$name"
}

# Movies are dated by the "(Year)" ending their folder name, shows by the
# first-aired date in series.xml. Undated titles sort after every date.
_planDateKey() {
    local kind="$1" folder="$2" title="${2##*/}" value
    if [[ "$kind" == movies ]]; then
        if [[ "$title" =~ \(([12][0-9]{3})\)[[:space:]]*$ ]]; then
            printf '%s' "${BASH_REMATCH[1]}"
            return
        fi
    else
        value="$(_planXmlValue "$folder/series.xml" FirstAired)"
        if [[ "$value" =~ ^([12][0-9]{3}(-[0-9]{2}-[0-9]{2})?) ]]; then
            printf '%s' "${BASH_REMATCH[1]}"
            return
        fi
    fi
    printf '~'
}

_planPercent() {
    local tenths=$(($1 * 1000 / $2))
    printf '%d.%d%%' "$((tenths / 10))" "$((tenths % 10))"
}

_planReport() {
    local name="$1" prefix="$2" mount="$3" used="$4" total="$5" remaining="$6" target="$7" forced="$8"
    local airingCount="$9" airingBytes="${10}" item
    shift 10
    _sayField "Disk:" "$mount $(_planPercent "$used" "$total") used ($(_bytesFormat "$used") of $(_bytesFormat "$total")), target ${mapRebalance[$name]}%"
    if [[ "${mapType[$name]}" == tv ]]; then
        _sayField "Kept local:" "$airingCount airing shows ($(_bytesFormat "$airingBytes")); only ended shows move"
    fi
    for item in "$@"; do
        _sayField "Split:" "$(_manifestPathShow "$item") is airing and also on $destPlace; left in place"
    done
    if ((planCount == 0)); then
        _sayField "Plan:" "nothing to move"
        return 0
    fi
    _sayField "Plan:" "$planCount titles, $(_bytesFormat "$planBytes") ($forced already on $destPlace)"
    _sayField "After move:" "$(_planPercent "$remaining" "$total") used"
    if ((remaining > target)); then
        _sayField "SHORTFALL:" "eligible titles bring $mount only to $(_planPercent "$remaining" "$total") (target ${mapRebalance[$name]}%)"
    fi
    _say "  Planned titles (oldest first):"
    _reportExcerpt "$prefix.plan.report"
}

_planSelect() {
    local prefix="$1" title="$2" key="$3" size="$4" reason="$5"
    printf '%s\0' "$title" >>"$prefix.plan"
    printf '%-10s %10s  %s (%s)\n' "${key/\~/undated}" "$(_bytesFormat "$size")" "$(_manifestPathShow "$title")" "$reason" \
        >>"$prefix.plan.report"
    planCount=$((planCount + 1))
    planBytes=$((planBytes + size))
}

# Orders "key<TAB>title" entries: titles already on the destination first, then
# by date key and name. Prints them NUL-terminated.
_planSortAlreadyThenOldest() {
    local -n onDestRef="$1"
    local entry rank
    shift
    for entry in "$@"; do
        rank=1
        [[ -n "${onDestRef[${entry#*$'\t'}]:-}" ]] && rank=0
        printf '%s\t%s\0' "$rank" "$entry"
    done | LC_ALL=C sort -z -t $'\t' -k1,1 -k2,2 -k3 | while IFS= read -r -d '' entry; do
        printf '%s\0' "${entry#*$'\t'}"
    done
}

# Reads the first value of a simple XML element, trimmed. Empty when the file
# or element is missing.
_planXmlValue() {
    local file="$1" tag="$2" value
    [[ -f "$file" ]] || return 0
    value="$(sed -n "s:.*<$tag>\([^<]*\)</$tag>.*:\1:p" -- "$file" 2>/dev/null | head -n 1)"
    value="${value#"${value%%[![:space:]]*}"}"
    printf '%s' "${value%"${value##*[![:space:]]}"}"
}
