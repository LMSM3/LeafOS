#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LeafOS LAN discovery engine -- core/net/discover.py

Active discovery methods (no external dependencies, stdlib only):
  subnet_scan   -- concurrent SSH probes across a CIDR range
  arp_hosts     -- read ARP/neighbour table for LAN-reachable IPs
  ping_filter   -- ICMP pre-filter to drop non-responding hosts fast

CLI commands exposed (called by core/net/net.sh and bin/leafctl):
  scan SUBNET [options]   -- run the full scan pipeline
  arp                     -- print ARP-reachable hosts
  ping SUBNET             -- ICMP sweep only

All output is machine-readable JSON or human-readable table.
Auto-registration writes directly into the caller's nodes.json via the
leaf_node.py registry helpers (no jq dependency).
"""

import argparse
import json
import os
import socket
import struct
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

# ---------------------------------------------------------------------------
# UTF-8 safety (cp1252 environments)
# ---------------------------------------------------------------------------
for _s in ("stdout", "stderr"):
    _st = getattr(sys, _s, None)
    _rc = getattr(_st, "reconfigure", None)
    if _rc:
        try:
            _rc(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            pass

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.join(_HERE, "..", "node", "leaf_node.py")


def _ts():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _py():
    for cand in ("python3", "python"):
        if subprocess.run(
            [cand, "--version"], capture_output=True
        ).returncode == 0:
            return cand
    raise RuntimeError("python3 not found")


def _leaf_home():
    ev = os.environ.get("LEAF_HOME")
    if ev:
        return os.path.abspath(os.path.expanduser(ev))
    return os.path.abspath(os.path.expanduser("~/.leaf"))


# ---------------------------------------------------------------------------
# Subnet expansion
# ---------------------------------------------------------------------------
def _ip_to_int(ip):
    packed = socket.inet_aton(ip)
    return struct.unpack("!I", packed)[0]


def _int_to_ip(n):
    return socket.inet_ntoa(struct.pack("!I", n))


def expand_subnet(cidr):
    """Yield all host IPs in a CIDR block (e.g. 192.168.1.0/24).
    Accepts plain IP (treated as /32), range 192.168.1.1-50, or CIDR."""
    # plain IP
    if "/" not in cidr and "-" not in cidr:
        try:
            socket.inet_aton(cidr)
            yield cidr
            return
        except socket.error:
            raise ValueError("invalid IP/CIDR: {}".format(cidr))

    # simple range: 192.168.1.1-50
    if "-" in cidr and "/" not in cidr:
        base, end_part = cidr.rsplit("-", 1)
        base_parts = base.split(".")
        start_host = int(base_parts[-1])
        end_host = int(end_part.strip())
        prefix = ".".join(base_parts[:-1])
        for h in range(start_host, end_host + 1):
            yield "{}.{}".format(prefix, h)
        return

    # CIDR
    ip_part, bits_str = cidr.split("/")
    bits = int(bits_str)
    if bits > 32 or bits < 0:
        raise ValueError("invalid prefix length: {}".format(bits))
    network = _ip_to_int(ip_part) & (0xFFFFFFFF << (32 - bits))
    total = 1 << (32 - bits)
    # skip network address and broadcast
    for offset in range(1, total - 1):
        yield _int_to_ip(network + offset)


# ---------------------------------------------------------------------------
# ICMP ping pre-filter
# ---------------------------------------------------------------------------
def _ping_one(ip, timeout=1):
    """Return True if ip responds to ping. Cross-platform (Linux/macOS/Windows)."""
    import platform
    try:
        if platform.system() == "Windows":
            cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(timeout), ip]
        r = subprocess.run(cmd, capture_output=True, timeout=timeout + 2)
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def ping_filter(ips, timeout=1, max_workers=64):
    """Return subset of ips that respond to ICMP ping."""
    alive = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_ping_one, ip, timeout): ip for ip in ips}
        for fut in as_completed(futures):
            ip = futures[fut]
            try:
                if fut.result():
                    alive.append(ip)
            except Exception:
                pass
    return alive


# ---------------------------------------------------------------------------
# ARP table reader
# ---------------------------------------------------------------------------
def arp_hosts():
    """Return list of IPs present in the local ARP/neighbour table."""
    hosts = []

    # Linux: /proc/net/arp
    proc_arp = "/proc/net/arp"
    if os.path.isfile(proc_arp):
        with open(proc_arp, encoding="ascii", errors="replace") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 4 and parts[0] != "IP" and parts[2] != "0x0":
                    hosts.append(parts[0])
        return hosts

    # macOS / BSD: arp -n
    try:
        out = subprocess.check_output(
            ["arp", "-n"], stderr=subprocess.DEVNULL, universal_newlines=True, timeout=5
        )
        for line in out.splitlines():
            parts = line.split()
            if parts and "." in parts[0] and parts[0] != "Address":
                # filter incomplete entries
                if len(parts) >= 3 and parts[2] not in ("(incomplete)", "incomplete"):
                    hosts.append(parts[0])
        return hosts
    except Exception:
        pass

    # Windows: arp -a (basic parse)
    try:
        out = subprocess.check_output(
            ["arp", "-a"], stderr=subprocess.DEVNULL, universal_newlines=True, timeout=5
        )
        for line in out.splitlines():
            parts = line.split()
            if parts and "." in parts[0]:
                try:
                    socket.inet_aton(parts[0])
                    hosts.append(parts[0])
                except socket.error:
                    pass
        return hosts
    except Exception:
        pass

    return hosts


# ---------------------------------------------------------------------------
# SSH leaf probe
# ---------------------------------------------------------------------------
def _probe_one(ip, user, ssh_opts_list, timeout, leaf_cmd):
    """SSH into ip and run 'leaf node status --json'. Return parsed dict or None."""
    ssh_args = ["ssh"] + ssh_opts_list + [
        "-o", "ConnectTimeout={}".format(timeout),
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "{}@{}".format(user, ip),
        "{} node status --json".format(leaf_cmd),
    ]
    try:
        r = subprocess.run(
            ssh_args,
            capture_output=True,
            text=True,
            timeout=timeout + 2,
        )
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout.strip())
        if data.get("leafos_object") == "node_status":
            data["_ip"] = ip
            return data
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        pass
    return None


def subnet_scan(
    cidr,
    user="leaf",
    ssh_opts=None,
    timeout=3,
    max_workers=32,
    use_ping=False,
    use_arp=False,
    leaf_cmd="leaf",
    verbose=False,
):
    """Scan cidr for Leaf nodes via SSH probe.

    Returns list of dicts: [{ip, node_id, state, tasks_running, ...}]
    """
    ssh_opts_list = (ssh_opts or "").split() if ssh_opts else []

    # inherit LEAF_SSH_OPTS from environment if not overridden
    env_opts = os.environ.get("LEAF_SSH_OPTS", "")
    if env_opts and not ssh_opts:
        ssh_opts_list = env_opts.split()

    # build IP candidate list
    candidates = list(expand_subnet(cidr))
    if verbose:
        print(
            json.dumps({"event": "scan_start", "cidr": cidr,
                        "candidates": len(candidates), "ts": _ts()}),
            flush=True,
        )

    # ARP pre-filter
    if use_arp:
        arp_set = set(arp_hosts())
        candidates = [ip for ip in candidates if ip in arp_set]
        if verbose:
            print(json.dumps({"event": "arp_filter", "remaining": len(candidates)}),
                  flush=True)

    # ICMP pre-filter
    if use_ping:
        candidates = ping_filter(candidates, timeout=1, max_workers=max_workers)
        if verbose:
            print(json.dumps({"event": "ping_filter", "remaining": len(candidates)}),
                  flush=True)

    # SSH leaf probe (concurrent)
    found = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(_probe_one, ip, user, ssh_opts_list, timeout, leaf_cmd): ip
            for ip in candidates
        }
        for fut in as_completed(futures):
            ip = futures[fut]
            try:
                result = fut.result()
                if result:
                    found.append(result)
                    if verbose:
                        print(json.dumps({"event": "found", "ip": ip,
                                          "node_id": result.get("node_id")}),
                              flush=True)
            except Exception as exc:
                if verbose:
                    print(json.dumps({"event": "probe_error", "ip": ip,
                                      "error": str(exc)}),
                          flush=True)

    found.sort(key=lambda d: _ip_to_int(d["_ip"]))
    return found


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------
def _register_node(home, name, ip, user, path, ssh_opts, dry_run=False):
    """Add a discovered node to nodes.json via leaf_node.py registry-add."""
    py = _py()
    args = [py, _ENGINE, "registry-add", name, "{}@{}".format(user, ip),
            "--transport", "ssh", "--path", path]
    if ssh_opts:
        args += ["--ssh-opts", ssh_opts]
    if dry_run:
        print(json.dumps({"event": "would_register", "name": name,
                          "target": "{}@{}".format(user, ip)}))
        return
    env = dict(os.environ, LEAF_HOME=home)
    subprocess.run(args, env=env, check=True)


def auto_register(found, user, path, ssh_opts, home, dry_run=False):
    """Register all found nodes. Derives name from node_id, deduplicates."""
    seen_names = set()
    for node in found:
        node_id = node.get("node_id", node["_ip"].replace(".", "-"))
        name = node_id
        # deduplicate: if name already seen, append last IP octet
        if name in seen_names:
            name = "{}-{}".format(node_id, node["_ip"].split(".")[-1])
        seen_names.add(name)
        _register_node(home, name, node["_ip"], user, path, ssh_opts, dry_run)


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------
def _print_table(found):
    if not found:
        print("  no leaf nodes found")
        return
    col_ip = max(len(d["_ip"]) for d in found)
    col_id = max(len(d.get("node_id", "?")) for d in found)
    fmt = "  {:<{}} {:<{}} {:<8} running={}"
    for d in found:
        print(fmt.format(
            d["_ip"], col_ip,
            d.get("node_id", "?"), col_id,
            d.get("state", "?"),
            d.get("tasks_running", "?"),
        ))


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------
def cmd_scan(args):
    found = subnet_scan(
        cidr=args.subnet,
        user=args.user,
        ssh_opts=args.ssh_opts,
        timeout=args.timeout,
        max_workers=args.concurrency,
        use_ping=args.ping_first,
        use_arp=args.arp,
        leaf_cmd=os.environ.get("LEAF_REMOTE_CMD", "leaf"),
        verbose=args.verbose,
    )

    if args.json:
        # strip internal _ip field only if not useful; keep it for --register
        out = []
        for d in found:
            row = dict(d)
            row["ip"] = row.pop("_ip")
            out.append(row)
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        _print_table(found)

    if args.register:
        home = _leaf_home()
        auto_register(found, args.user, args.path, args.ssh_opts,
                      home, dry_run=args.dry_run)
        if not args.json:
            print("\n  {} node(s) {}registered".format(
                len(found), "would be " if args.dry_run else ""))

    return 0 if found else 1


def cmd_arp(args):
    hosts = arp_hosts()
    if args.json:
        print(json.dumps({"arp_hosts": hosts}))
    else:
        for h in hosts:
            print("  {}".format(h))
    return 0


def cmd_ping(args):
    ips = list(expand_subnet(args.subnet))
    alive = ping_filter(ips, timeout=args.timeout)
    alive.sort(key=_ip_to_int)
    if args.json:
        print(json.dumps({"alive": alive, "total": len(ips)}))
    else:
        for ip in alive:
            print("  {}".format(ip))
        print("  {}/{} responded".format(len(alive), len(ips)))
    return 0


# ---------------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="discover.py",
        description="LeafOS LAN discovery engine",
    )
    sub = p.add_subparsers(dest="cmd")

    # scan
    sc = sub.add_parser("scan", help="SSH-probe a subnet for Leaf nodes")
    sc.add_argument("subnet", help="CIDR (192.168.1.0/24), range (192.168.1.1-50), or IP")
    sc.add_argument("--user", default=os.environ.get("LEAF_SCAN_USER", "leaf"),
                    help="SSH user (default: leaf / $LEAF_SCAN_USER)")
    sc.add_argument("--ssh-opts", default=os.environ.get("LEAF_SSH_OPTS", ""),
                    help="extra SSH options (default: $LEAF_SSH_OPTS)")
    sc.add_argument("--timeout", type=int, default=3,
                    help="SSH connect timeout in seconds (default: 3)")
    sc.add_argument("--concurrency", type=int, default=32,
                    help="concurrent SSH probes (default: 32)")
    sc.add_argument("--ping-first", action="store_true",
                    help="pre-filter with ICMP ping")
    sc.add_argument("--arp", action="store_true",
                    help="pre-filter using local ARP table")
    sc.add_argument("--register", action="store_true",
                    help="auto-register found nodes into nodes.json")
    sc.add_argument("--dry-run", action="store_true",
                    help="show what would be registered without writing")
    sc.add_argument("--path", default="~/.leaf",
                    help="remote LEAF_HOME path for registered nodes")
    sc.add_argument("--json", action="store_true", help="JSON output")
    sc.add_argument("--verbose", action="store_true",
                    help="stream probe events as JSONL during scan")

    # arp
    ar = sub.add_parser("arp", help="Print ARP-table hosts")
    ar.add_argument("--json", action="store_true")

    # ping
    pg = sub.add_parser("ping", help="ICMP sweep a subnet")
    pg.add_argument("subnet")
    pg.add_argument("--timeout", type=int, default=1)
    pg.add_argument("--json", action="store_true")

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return 1
    dispatch = {"scan": cmd_scan, "arp": cmd_arp, "ping": cmd_ping}
    return dispatch[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
