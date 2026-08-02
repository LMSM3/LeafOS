# LeafOS Networking Guide

Version: 0.5.0

Covers LAN discovery, distribution, node registration, SSH transport, and
access control.  All networking is terminal-only — no web server, no browser.

Scope: optional node and distribution subsystem. The resident local project
stack operates on loopback plus local files and does not require LAN setup.
Provider serving is configured separately in `vulkan-provider-stack.json`;
TUI controls use an authenticated ephemeral loopback bridge.

---

## Contents

1. [Network overview](#network-overview)
2. [LAN discovery](#lan-discovery)
3. [Serving and downloading](#serving-and-downloading)
4. [Node registration](#node-registration)
5. [SSH transport](#ssh-transport)
6. [Access control](#access-control)
7. [Troubleshooting](#troubleshooting)

---

## Network overview

```
  ┌─────────────────────────────────────────────────────────────┐
  │                       Your LAN                              │
  │                                                             │
  │   MiniPC (192.168.4.44)          gpu1 (192.168.4.45)       │
  │   ┌──────────────────┐           ┌──────────────────┐      │
  │   │ leaf serve       │──HTTP──▶  │ leaf download    │      │
  │   │ leaf dashboard   │           │ leaf node init   │      │
  │   │ LEAF_HOME=~/.leaf│◀──SSH──   │ LEAF_HOME=~/.leaf│      │
  │   └──────────────────┘           └──────────────────┘      │
  │                                                             │
  │   leaf nodes scan 192.168.4.0/22                           │
  │   leaf nodes arp                                            │
  └─────────────────────────────────────────────────────────────┘
```

LeafOS uses two protocols:

| Protocol | Direction      | Purpose                         |
|----------|----------------|---------------------------------|
| SSH      | master → worker| task dispatch, result retrieval |
| HTTP     | any → server   | package distribution (serve)    |

---

## LAN discovery

### ARP table read (instant, passive)

```sh
leaf nodes arp
```

Reads the kernel ARP/neighbour table.  Returns unicast LAN IPs that the local
machine has recently communicated with.  No network packets sent.

Sources in order:
1. `/proc/net/arp` (Linux)
2. `arp -n` (macOS / BSD)
3. `arp -a` (Windows) — only `dynamic` and `static` entries; multicast and
   broadcast filtered

### ICMP ping sweep (fast, active)

```sh
leaf nodes ping-sweep 192.168.4.0/22
leaf nodes ping-sweep 192.168.4.1-20 --json
```

Sends ICMP echo to every address in the range concurrently (64 threads).
Returns hosts that responded.  Does **not** tell you whether Leaf is installed.

Subnet formats accepted:
- CIDR: `192.168.4.0/22`
- Range: `192.168.4.1-50`
- Single IP: `192.168.4.45`

### SSH scan (authoritative, active)

```sh
leaf nodes scan 192.168.4.0/22
leaf nodes scan 192.168.4.0/22 --ping-first --register
```

For each address, attempts `ssh … cat LEAF_HOME/node.json`.  A successful
response proves Leaf is installed and reachable.

| Option          | Effect                                          |
|-----------------|-------------------------------------------------|
| `--ping-first`  | ICMP pre-filter — skip hosts that don't respond |
| `--arp`         | ARP pre-filter — only probe ARP-table hosts     |
| `--user U`      | SSH username (default: current user)            |
| `--timeout N`   | seconds per SSH attempt (default: 5)            |
| `--concurrency N`| parallel threads (default: 16)                |
| `--register`    | auto-add discovered nodes to `nodes.json`       |
| `--dry-run`     | show what would be registered                   |
| `--json`        | JSON output                                     |

**Decision (DEC-003):** SSH probe is authoritative.  A host that responds to
ping but not SSH is not considered a valid Leaf node.

### Combined pipeline (fastest full scan)

```sh
# Step 1: ARP — instant, zero packets
leaf nodes arp

# Step 2: ping-sweep — confirm reachability
leaf nodes ping-sweep 192.168.4.0/22

# Step 3: SSH scan — verify Leaf + optionally register
leaf nodes scan 192.168.4.0/22 --arp --ping-first --register
```

---

## Serving and downloading

### Start a serve node

```sh
leaf serve                              # build bundles, serve on LAN IP:7771
leaf serve --port 8080                  # custom port
leaf serve --host 0.0.0.0              # bind all interfaces
leaf serve --once                       # stop after first download completes
leaf serve --no-rebuild                 # re-use existing dist/ bundles
```

While serving, the terminal shows the live banner with file sizes, SHA256
fingerprints, and the exact `leaf download` command to run on other machines.

### Build bundles without serving

```sh
leaf dist-build                  # writes to dist/
leaf dist-build --out /tmp/pkg   # custom output dir
```

Output files:

| File                    | Format   | Use case           |
|-------------------------|----------|--------------------|
| `leafos-0.5.0.tar.gz`   | tar+gzip | Linux / macOS / WSL|
| `leafos-0.5.0.zip`      | zip      | Windows            |
| `manifest.json`         | JSON     | checksum index     |

### Download from a serve node

```sh
# auto-select .tar.gz, save to current directory
leaf download 192.168.4.44

# specific file and destination
leaf download 192.168.4.44 leafos-0.5.0.zip --dest ~/Downloads

# custom port
leaf download 192.168.4.44:8080
```

Downloads stream with a real-time progress bar:

```
  [████████████████████████████░░░░░░░░░░░░] 71.2%  8.8 MB  2.1 MB/s
  done in 4.2s  →  /tmp/leafos-0.5.0.tar.gz
  verifying sha256 ...  OK
```

SHA256 is always verified.  A mismatch prints both expected and actual hashes
and exits non-zero.

### Inspect a remote manifest

```sh
leaf dist-info 192.168.4.44
```

```json
{
  "leafos_object": "manifest",
  "version": "0.5.0",
  "built_at": "2026-06-22T15:14:00-07:00",
  "host_ip": "192.168.4.44",
  "bundles": [
	{ "name": "leafos-0.5.0.tar.gz", "size": 1258291, "sha256": "a3f8..." },
	{ "name": "leafos-0.5.0.zip",    "size": 1318912, "sha256": "9c12..." }
  ]
}
```

---

## Node registration

Registered nodes are stored in `LEAF_HOME/nodes.json`.

### Manual registration

```sh
leaf nodes add gpu1   user@192.168.4.45
leaf nodes add local1 /tmp/worker1 --transport local
leaf nodes add remote1 user@192.168.4.46 --path /opt/leaf
```

### Auto-registration via scan

```sh
leaf nodes scan 192.168.4.0/22 --register
```

Each discovered node is named `leaf-<last-two-octets>` by default
(e.g., `leaf-4-45`).  If the remote `node.json` contains a `node_id`, that is
used instead.  Duplicate names get an incrementing suffix.

### List registered nodes

```sh
leaf nodes list
leaf nodes list --json
```

---

## SSH transport

LeafOS uses standard OpenSSH for all node-to-node communication.  No daemon
is required on the worker beyond `sshd`.

### Key setup (recommended)

```sh
ssh-keygen -t ed25519 -f ~/.ssh/leaf_ed25519 -N ""
ssh-copy-id -i ~/.ssh/leaf_ed25519.pub user@192.168.4.45
```

Tell Leaf to use the key:

```sh
export LEAF_SSH_OPTS="-i ~/.ssh/leaf_ed25519 -o StrictHostKeyChecking=accept-new"
```

Or add it to `~/.ssh/config`:

```
Host 192.168.4.*
	User youruser
	IdentityFile ~/.ssh/leaf_ed25519
	StrictHostKeyChecking accept-new
```

### ProxyJump (reach nodes behind NAT)

```sh
# Register a node reachable through a bastion:
leaf nodes add private1 user@10.0.0.5

# Set LEAF_SSH_OPTS to use a jump host:
export LEAF_SSH_OPTS="-J bastion.example.com"
```

### Timeout tuning

```sh
export LEAF_SSH_OPTS="-o ConnectTimeout=3 -o ServerAliveInterval=10"
```

---

## Access control

### Restrict the leaf SSH key

Add to `~/.ssh/authorized_keys` on the worker (all on one line):

```
command="leaf task start $(cat -)",no-port-forwarding,no-X11-forwarding \
  ssh-ed25519 AAAA... leaf-controller
```

This limits the key to only running `leaf task start`; it cannot open a shell.

### Network-level restriction

Serve only on the LAN interface:

```sh
leaf serve --host 192.168.4.44
```

Or bind to loopback for testing:

```sh
leaf serve --host 127.0.0.1
```

---

## Troubleshooting

### `leaf nodes scan` finds nothing

1. Confirm the target has `sshd` running and a Leaf workspace:
   ```sh
   ssh user@192.168.4.45 "cat ~/.leaf/node.json"
   ```
2. Try `--timeout 10` for slow networks.
3. Check `LEAF_SSH_OPTS` for key or host-key errors.

### `leaf download` hangs

- Confirm `leaf serve` is running on the source node.
- Check firewall rules for port 7771.
- Try `leaf dist-info HOST` first — if that returns JSON, the server is up.

### ARP table is empty

On Windows, `arp -a` may return only the local subnet.  Try pinging a few
addresses first to populate the table:

```sh
ping 192.168.4.1
leaf nodes arp
```

### SHA256 mismatch on download

- Interrupted transfer: re-run `leaf download`.
- Rebuilt bundle on server mid-transfer: wait for build to finish, then download.
- Disk corruption: check disk health, then re-download.
