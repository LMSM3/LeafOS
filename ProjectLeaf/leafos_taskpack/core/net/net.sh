#!/usr/bin/env bash
# core/net/net.sh -- LAN discovery wrapper (active scan, ARP, ICMP)
set -u
_NET_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$_NET_DIR/../node/node.sh"

LEAF_DISCOVER_PY="$_NET_DIR/discover.py"

_discover() {
    local py; py="$(_leaf_py)"
    "$py" "$LEAF_DISCOVER_PY" "$@"
}

# leaf_net_scan SUBNET [OPTIONS...]
leaf_net_scan() {
    local subnet="${1:-}"; [[ -n "$subnet" ]] || brand_die "nodes scan requires SUBNET (e.g. 192.168.1.0/24)"
    shift || true
    brand_header "nodes scan $subnet"
    _discover scan "$subnet" "$@"
}

# leaf_net_arp
leaf_net_arp() {
    brand_header "arp hosts"
    _discover arp "$@"
}

# leaf_net_ping SUBNET
leaf_net_ping() {
    local subnet="${1:-}"; [[ -n "$subnet" ]] || brand_die "nodes ping-sweep requires SUBNET"
    shift || true
    brand_header "ping sweep $subnet"
    _discover ping "$subnet" "$@"
}
