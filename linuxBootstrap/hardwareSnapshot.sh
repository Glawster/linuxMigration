#!/usr/bin/env bash
set -euo pipefail

HOST="$(hostname -s)"
STATE_ROOT="${XDG_STATE_HOME:-$HOME/.local/state}/hardwareSnapshot/${HOST}"
SNAPSHOT_ROOT="$STATE_ROOT/snapshots"
DIFF_ROOT="$STATE_ROOT/diffs"
TEMP_HISTORY="$STATE_ROOT/temperatures.csv"
STAMP="$(date '+%Y-%m-%d_%H%M%S')"
ISO_TIME="$(date --iso-8601=seconds)"

mkdir -p "$SNAPSHOT_ROOT" "$DIFF_ROOT"

usage() {
    cat <<'USAGE'
Usage: hardwareSnapshot [--temps|--diff|--history|--help]

With no option, capture a full hardware snapshot, append temperature history,
and compare stable hardware configuration with the previous snapshot.

  --temps    collect and display temperatures only
  --diff     display the most recent hardware configuration diff
  --history  list saved snapshots and temperature-history location
  --help     show this help
USAGE
}

rootCommand() {
    if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
        "$@"
    elif command -v sudo >/dev/null 2>&1; then
        sudo "$@"
    else
        return 1
    fi
}

statusForHddTemp() {
    local temp="$1"
    if (( temp > 45 )); then
        printf 'HOT'
    elif (( temp > 40 )); then
        printf 'WARM'
    else
        printf 'NORMAL'
    fi
}

ensureTempHeader() {
    if [[ ! -f "$TEMP_HISTORY" ]]; then
        printf 'timestamp,kind,device,sensor,temp_c,status\n' > "$TEMP_HISTORY"
    fi
}

csvSafe() {
    local value="$1"
    value="${value//\"/\"\"}"
    printf '"%s"' "$value"
}

collectSensorTemps() {
    local outputFile="$1"
    command -v sensors >/dev/null 2>&1 || return 0

    sensors > "$outputFile" 2>&1 || true
    sensors -u 2>/dev/null | awk '
        /^[^[:space:]]/ { chip=$0; label=""; next }
        /^[[:space:]]+[^:]+:$/ {
            label=$0
            sub(/^[[:space:]]+/, "", label)
            sub(/:$/, "", label)
            next
        }
        /^[[:space:]]+temp[0-9]+_input:/ {
            printf "%s\t%s\t%s\n", chip, label, $2
        }
    '
}

collectDiskTemps() {
    local outputFile="$1"
    command -v smartctl >/dev/null 2>&1 || return 0

    : > "$outputFile"
    while read -r device type; do
        [[ "$type" == "disk" ]] || continue

        local model serial rota identity smart temp status
        model="$(lsblk -dn -o MODEL "$device" 2>/dev/null | xargs || true)"
        serial="$(lsblk -dn -o SERIAL "$device" 2>/dev/null | xargs || true)"
        rota="$(lsblk -dn -o ROTA "$device" 2>/dev/null | xargs || true)"
        identity="${serial:-${model:-$device}}"

        smart="$(rootCommand smartctl -A "$device" 2>/dev/null || true)"
        [[ -n "$smart" ]] || continue

        temp="$(awk '
            /Temperature_Celsius|Airflow_Temperature_Cel/ {print $10; exit}
            /Current Drive Temperature:/ {gsub(/[^0-9]/,"",$4); print $4; exit}
        ' <<< "$smart")"

        if [[ -z "$temp" ]]; then
            temp="$(rootCommand smartctl -x "$device" 2>/dev/null | awk '
                /Temperature:/ {for (i=2;i<=NF;i++) if ($i ~ /^[0-9]+$/) {print $i; exit}}
            ' || true)"
        fi

        [[ "$temp" =~ ^[0-9]+([.][0-9]+)?$ ]] || continue
        if [[ "$rota" == "1" ]]; then
            status="$(statusForHddTemp "${temp%.*}")"
        else
            status="MEASURED"
        fi

        printf '%s\t%s\t%s\t%s\t%s\n' "$identity" "$model" "$device" "$temp" "$status"
        printf '%s: %s°C (%s) [%s]\n' "$identity" "$temp" "$status" "$device" >> "$outputFile"
    done < <(lsblk -dn -o PATH,TYPE 2>/dev/null)
}

appendTemperatures() {
    local snapshotDir="$1"
    local sensorRows diskRows
    sensorRows="$(mktemp)"
    diskRows="$(mktemp)"
    trap 'rm -f "$sensorRows" "$diskRows"' RETURN

    ensureTempHeader

    collectSensorTemps "$snapshotDir/sensors.txt" > "$sensorRows"
    collectDiskTemps "$snapshotDir/disk-temperatures.txt" > "$diskRows"

    echo "Temperatures"
    echo "------------"

    if [[ -s "$sensorRows" ]]; then
        while IFS=$'\t' read -r chip sensor temp; do
            printf '%-28s %6s°C\n' "${chip}: ${sensor:-temperature}" "$temp"
            printf '%s,sensor,%s,%s,%s,MEASURED\n' \
                "$(csvSafe "$ISO_TIME")" "$(csvSafe "$chip")" "$(csvSafe "${sensor:-temperature}")" "$temp" >> "$TEMP_HISTORY"
        done < "$sensorRows"
    fi

    if [[ -s "$diskRows" ]]; then
        while IFS=$'\t' read -r identity model device temp status; do
            printf '%-28s %6s°C  %s\n' "$identity" "$temp" "$status"
            printf '%s,disk,%s,%s,%s,%s\n' \
                "$(csvSafe "$ISO_TIME")" "$(csvSafe "$identity")" "$(csvSafe "${model:-disk}")" "$temp" "$status" >> "$TEMP_HISTORY"
        done < "$diskRows"
    fi

    if [[ ! -s "$sensorRows" && ! -s "$diskRows" ]]; then
        echo "No temperature readings available."
    fi

    echo
    echo "Temperature history: $TEMP_HISTORY"
}

captureConfiguration() {
    local file="$1"
    {
        echo "# Host"
        hostnamectl 2>/dev/null | grep -E 'Hardware Vendor|Hardware Model|Firmware Version' || true

        echo
        echo "# CPU"
        lscpu 2>/dev/null | grep -E 'Model name:|Socket\(s\):|Core\(s\) per socket:|Thread\(s\) per core:|Architecture:' || true

        echo
        echo "# Memory modules"
        if command -v dmidecode >/dev/null 2>&1; then
            rootCommand dmidecode --type memory 2>/dev/null | grep -E '^\s*(Size|Type|Speed|Configured Memory Speed|Manufacturer|Serial Number|Part Number):' || true
        fi

        echo
        echo "# BIOS"
        if command -v dmidecode >/dev/null 2>&1; then
            rootCommand dmidecode --type bios 2>/dev/null | grep -E '^\s*(Vendor|Version|Release Date):' || true
        fi

        echo
        echo "# PCI devices"
        lspci -nn 2>/dev/null | sort || true

        echo
        echo "# Storage devices"
        lsblk -dn -o MODEL,SERIAL,SIZE,TYPE,TRAN 2>/dev/null | sed 's/[[:space:]]\+$//' | sort || true

        echo
        echo "# Network interfaces"
        for iface in /sys/class/net/*; do
            [[ -e "$iface/address" ]] || continue
            printf '%s %s\n' "$(basename "$iface")" "$(cat "$iface/address")"
        done | sort
    } > "$file"
}

captureStatus() {
    local dir="$1"
    uname -a > "$dir/uname.txt"
    lscpu > "$dir/cpu.txt" 2>&1 || true
    free -h > "$dir/memory.txt" 2>&1 || true
    lspci -nnk > "$dir/pci.txt" 2>&1 || true
    lsblk -o NAME,MODEL,SERIAL,SIZE,TYPE,FSTYPE,MOUNTPOINTS > "$dir/storage.txt" 2>&1 || true
    ip address show > "$dir/network.txt" 2>&1 || true
    ip link show > "$dir/network-link.txt" 2>&1 || true
    if command -v dmidecode >/dev/null 2>&1; then
        rootCommand dmidecode --type baseboard > "$dir/dmi-baseboard.txt" 2>&1 || true
        rootCommand dmidecode --type bios > "$dir/dmi-bios.txt" 2>&1 || true
        rootCommand dmidecode --type memory > "$dir/dmi-memory.txt" 2>&1 || true
        rootCommand dmidecode --type system > "$dir/dmi-system.txt" 2>&1 || true
    fi
}

latestSnapshot() {
    [[ -L "$STATE_ROOT/latest" ]] && readlink -f "$STATE_ROOT/latest"
}

showLatestDiff() {
    local latestDiff
    latestDiff="$(find "$DIFF_ROOT" -maxdepth 1 -type f -name '*.diff' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)"
    if [[ -n "$latestDiff" && -s "$latestDiff" ]]; then
        cat "$latestDiff"
    else
        echo "No saved hardware configuration differences."
    fi
}

showHistory() {
    echo "Snapshots for $HOST"
    find "$SNAPSHOT_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' 2>/dev/null | sort -r
    echo
    echo "Temperature history: $TEMP_HISTORY"
    echo "Diff history:        $DIFF_ROOT"
}

collectTempsOnly() {
    local tempDir="$STATE_ROOT/current"
    mkdir -p "$tempDir"
    appendTemperatures "$tempDir"
}

collectFullSnapshot() {
    local snapshotDir="$SNAPSHOT_ROOT/$STAMP"
    local previous diffFile
    previous="$(latestSnapshot || true)"
    mkdir -p "$snapshotDir"

    echo "Hardware snapshot: $HOST"
    echo "Saving to: $snapshotDir"
    echo

    captureConfiguration "$snapshotDir/configuration.txt"
    captureStatus "$snapshotDir"
    appendTemperatures "$snapshotDir"

    if [[ -n "$previous" && -f "$previous/configuration.txt" ]]; then
        diffFile="$DIFF_ROOT/$STAMP.diff"
        diff -u "$previous/configuration.txt" "$snapshotDir/configuration.txt" > "$diffFile" || true
        if [[ -s "$diffFile" ]]; then
            echo
            echo "Hardware configuration: CHANGED"
            echo "Diff: $diffFile"
        else
            rm -f "$diffFile"
            echo
            echo "Hardware configuration: UNCHANGED"
        fi
    else
        echo
        echo "Hardware configuration: BASELINE CREATED"
    fi

    ln -sfn "$snapshotDir" "$STATE_ROOT/latest"
}

case "${1:-}" in
    "") collectFullSnapshot ;;
    --temps) collectTempsOnly ;;
    --diff) showLatestDiff ;;
    --history) showHistory ;;
    --help|-h) usage ;;
    *) usage >&2; exit 2 ;;
esac
