#!/usr/bin/env bash

networkingApply() {
    local address="${1:-}" ip octet
    [[ -n "$address" ]] || return 0
    [[ "$address" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$ ]] || {
        logError "static IP must be IPv4 CIDR notation: $address"
        return 2
    }
    ip="${address%/*}"
    IFS=. read -r -a octets <<< "$ip"
    for octet in "${octets[@]}"; do
        ((10#$octet <= 255)) || { logError "static IP contains an invalid octet: $address"; return 2; }
    done
    logWarning "static IP requested ($address), but connection selection is not yet implemented"
}
