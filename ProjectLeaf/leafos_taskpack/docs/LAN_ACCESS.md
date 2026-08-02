# LeafOS — Local Network Access & Control

> **Scope:** optional SSH/LAN node subsystem. This document does not grant
> remote authority over the resident project inlet. The current local project
> workflow is `leafctl live PATH`; any future remote resident control must
> preserve typed requests, authentication, project boundaries, and validation.

> This document elaborates every method the Leaf node system uses, or can use,
> to find, reach, control, and secure nodes on a local network. It is a design
> map as much as a reference: each section names the mechanism, explains what
> it does, and says exactly how it maps to `leaf` commands and internals.

---

## 1. The Network Stack Leaf Uses (and Deliberately Does Not Use)

The current system builds its entire LAN control surface on three primitives:

```
ssh   — command execution and stdin/stdout pipes
scp   — file transfer (task files in, result files out)
tail  — log streaming (via an ssh-wrapped tail -f)
```

This choice is not laziness. SSH is installed on every serious UNIX machine,
handles auth, handles encryption, handles port-forwarding, handles proxying, and
has 30 years of hardening. Building on top of it means every security
improvement SSH gets is inherited for free.

What Leaf deliberately avoids:

| What | Why not |
|---|---|
| HTTP API on the node | needs a daemon, needs a port, needs auth on top |
| gRPC / protobuf | install complexity, compiled IDL, breaks POSIX simplicity |
| Redis / RabbitMQ | another service to manage, another thing to debug at 2 AM |
| WebSockets | implies a browser; Leaf is a shell system |
| nmap | external dependency, IDS alerts, not installed by default |
| mDNS via external lib | needs `zeroconf`/`avahi`, not stdlib, adds install step |

The rule: if `ssh` and Python stdlib can do it, nothing else is added to the
critical path.

---

## 2. Access Methods: The Full Map

```
┌─────────────────────────────────────────────────────────┐
│              LAN ACCESS & CONTROL METHODS               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ACTIVE DISCOVERY (master initiates)                    │
│  ├── 2.1  SSH probe scan (subnet sweep)                 │
│  ├── 2.2  ARP table read  (arp -n / ip neigh)           │
│  └── 2.3  ICMP ping sweep  (fast pre-filter)            │
│                                                         │
│  PASSIVE DISCOVERY (node advertises itself)             │
│  ├── 2.4  mDNS / Zeroconf  (_leaf._tcp.local)           │
│  └── 2.5  UDP beacon  (leaf node broadcast)             │
│                                                         │
│  REGISTRATION & REGISTRY                                │
│  ├── 2.6  Manual add  (leaf nodes add)          ← NOW   │
│  └── 2.7  Auto-register from scan result                │
│                                                         │
│  MULTI-HOP / PROXY ACCESS                               │
│  ├── 2.8  SSH ProxyJump  (-J user@bastion)              │
│  └── 2.9  SSH tunnel / port forward                     │
│                                                         │
│  ACCESS CONTROL                                         │
│  ├── 2.10 Dedicated SSH key per cluster                 │
│  ├── 2.11 authorized_keys command restriction           │
│  ├── 2.12 Per-node non-root user (leafrunner)           │
│  └── 2.13 Firewall: LAN-only SSH                        │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Active Discovery

### 3.1 SSH probe scan (`leaf nodes scan SUBNET`)

The primary active discovery mechanism. For each IP in the subnet range, the
scanner opens a short-timeout SSH connection and attempts to run
`leaf node status --json`. If the response is valid JSON with `"state": "ready"`,
the host is a live Leaf node.

```bash
leaf nodes scan 192.168.1.0/24
leaf nodes scan 192.168.1.0/24 --timeout 3 --concurrency 32
leaf nodes scan 192.168.1.0/24 --register          # auto-add found nodes
leaf nodes scan 192.168.1.0/24 --user sm --key ~/.ssh/leaf_node_key
```

Internally:

```
for each IP in subnet:
	concurrent SSH attempt: ssh -o ConnectTimeout=T IP "leaf node status --json"
	if response parses as valid node status JSON:
		emit result line
		if --register: leaf_node_engine registry-add NAME IP --transport ssh
```

Implementation lives in `core/net/discover.py`. Python's
`concurrent.futures.ThreadPoolExecutor` provides the concurrency — no
`asyncio`, no third-party libraries.

**What it produces:**

```
192.168.1.41  gpu-node-01  ready   tasks_running=0
192.168.1.42  gpu-node-02  ready   tasks_running=2
192.168.1.55  cpu-farm-01  ready   tasks_running=0
```

Or with `--json`:

```json
[
  {"ip": "192.168.1.41", "node_id": "gpu-node-01", "state": "ready", "tasks_running": 0},
  {"ip": "192.168.1.42", "node_id": "gpu-node-02", "state": "ready", "tasks_running": 2}
]
```

**Timeout strategy:**

```
ConnectTimeout   3 s   (SSH TCP handshake + key exchange)
CommandTimeout   2 s   (leaf node status is instant if node is healthy)
Total worst-case 5 s per host * 32 concurrent = /24 scanned in ~40 s
```

**Scanner respects `LEAF_SSH_OPTS`**, so a cluster key works automatically:

```bash
export LEAF_SSH_OPTS="-i ~/.ssh/leaf_node_key"
leaf nodes scan 192.168.1.0/24
```

### 3.2 ARP table read

The ARP table (`arp -n` or `ip neigh`) contains all IPs the master has recently
talked to on the LAN. This is a **zero-cost pre-filter**: instead of probing
256 hosts, probe only the ~20 that appear in ARP.

```bash
leaf nodes scan --arp            # probe ARP table entries only
leaf nodes scan --arp --register
```

Internally reads `/proc/net/arp` (Linux) or parses `arp -n` (macOS/BSD).
This is implemented in `discover.py` as `_arp_hosts()`.

### 3.3 ICMP ping pre-filter

A /24 has 254 hosts. Most are off. A fast ICMP ping sweep (1 s timeout, 1
packet) reduces the SSH probe set to only responding IPs.

```bash
leaf nodes scan 192.168.1.0/24 --ping-first
```

Uses `ping -c1 -W1 IP` via `subprocess`. On Linux, unprivileged ICMP works
from Python 3.3+ via `socket.SOCK_DGRAM` + `IPPROTO_ICMP`. On macOS it also
works without root. Falls back to `subprocess.run(["ping", ...])` if the socket
approach is unavailable.

**Sequence with all filters enabled:**

```
subnet IPs (254)
	 │
	 ├── ICMP ping filter  →  responding hosts (~20-50)
	 │        │
	 │        ├── ARP cache filter  →  known-recent hosts (~10-20)
	 │        │
	 │        └── SSH leaf probe  →  Leaf nodes (~2-10)
	 │
	 └── (non-responding hosts: skipped entirely)
```

---

## 4. Passive Discovery

Passive discovery inverts the model: **nodes announce themselves** rather than
waiting to be found. The master listens; nodes broadcast on join.

### 4.4 mDNS / Zeroconf (`_leaf._tcp.local`)

Nodes register a service `_leaf._tcp` on mDNS port 5353 (multicast UDP). The
master browses for `_leaf._tcp.local` and builds the registry automatically.

```bash
# on the node (advertises itself)
leaf node advertise            # sends mDNS _leaf._tcp.local record

# on the master (listens for advertisements)
leaf nodes discover --mdns     # browses _leaf._tcp.local until Ctrl-C
leaf nodes discover --mdns --register --timeout 10
```

**Why this needs a direction decision:** mDNS requires either:
- `avahi-daemon` (Linux system service, root configuration)
- `python-zeroconf` (pip install, breaks stdlib-only rule)
- Hand-rolled multicast UDP on 224.0.0.251:5353 (complex, fragile)

This is the fork. See Section 7 (Direction Choice).

### 4.5 UDP beacon (leaf node broadcast)

A simpler alternative to full mDNS. The node sends a periodic UDP packet on a
fixed LAN broadcast address (e.g. `255.255.255.255:7373` or subnet broadcast).
The master listens.

Beacon payload (JSONL line, no protocol overhead):

```json
{"event":"beacon","node_id":"gpu-node-01","version":"0.5.0","leaf_port":22,"hostname":"minipc","ts":"2026-06-21T14:00:00+00:00"}
```

```bash
leaf node beacon --interval 10        # node side: broadcast every 10 s
leaf nodes listen --timeout 30        # master side: collect beacons for 30 s
leaf nodes listen --register          # auto-add anything heard
```

**Advantages over mDNS:**
- Pure stdlib (`socket.SOCK_DGRAM`, `SO_BROADCAST`)
- No system daemon required
- No pip install
- Packet format is inspectable with `nc -ul 7373`

**Disadvantages:**
- Non-standard port (must be agreed on)
- Works only on same broadcast domain (no routing)
- Security: anyone on LAN can send fake beacons (must verify with subsequent SSH probe)

---

## 5. Registration & Registry

### 5.6 Manual `leaf nodes add` (current behavior)

```bash
leaf nodes add gpu1 sm@192.168.1.41
leaf nodes add gpu1 sm@192.168.1.41 --transport ssh --path ~/.leaf
```

Writes to `$LEAF_HOME/nodes.json`. Requires the operator to know the IP in
advance. This is the correct default: no automatic trust, no silent registration.

### 5.7 Auto-register from scan

With `--register`, a scan result automatically calls `registry-add`:

```bash
leaf nodes scan 192.168.1.0/24 --register --user sm
```

Auto-registered nodes get a name derived from their `node_id` field from
`leaf node status --json`. If two nodes share the same `node_id`, the IP is
appended: `gpu-node-01`, `gpu-node-01-192.168.1.42`.

The `--dry-run` flag shows what would be registered without writing anything:

```bash
leaf nodes scan 192.168.1.0/24 --register --dry-run
```

---

## 6. Multi-Hop & Proxy Access

### 6.8 SSH ProxyJump (`-J user@bastion`)

For nodes behind a bastion/jump host, SSH's `ProxyJump` option tunnels through:

```bash
# register a node behind a bastion
leaf nodes add gpu1 sm@10.0.0.41 \
	--ssh-opts "-J deploy@bastion.example.com"

# or via LEAF_SSH_OPTS
export LEAF_SSH_OPTS="-J deploy@bastion.example.com -i ~/.ssh/leaf_key"
leaf nodes ping gpu1
```

`remote.sh` expands `${LEAF_SSH_OPTS:-}` before all SSH/SCP calls, so
`ProxyJump` is automatically applied to task submit, watch, pull, and cancel.

The registry entry stores per-node SSH options:

```json
{
  "gpu1": {
	"target": "sm@10.0.0.41",
	"path": "~/.leaf",
	"transport": "ssh",
	"ssh_opts": "-J deploy@bastion.example.com -i ~/.ssh/leaf_key"
  }
}
```

`_node_resolve` reads `ssh_opts` and exports `_RSSH_OPTS`, which `_ssh()` and
`_scp()` use in preference to the global `LEAF_SSH_OPTS`.

### 6.9 SSH tunnel (local port-forward)

For networks where direct SSH to workers is blocked but port-forwarding is
allowed from the bastion:

```bash
# establish tunnel: local 2222 -> worker:22 through bastion
ssh -fNL 2222:10.0.0.41:22 deploy@bastion.example.com

# register via tunnel
leaf nodes add gpu1 sm@localhost --ssh-opts "-p 2222 -i ~/.ssh/leaf_key"
```

This is entirely transparent to the `leaf` command layer once the tunnel is up.

---

## 7. Access Control

### 7.10 Dedicated cluster SSH key

```bash
ssh-keygen -t ed25519 -C "leaf-cluster-$(date +%Y%m%d)" \
	-f ~/.ssh/leaf_node_key
# deploy to each worker
ssh-copy-id -i ~/.ssh/leaf_node_key.pub sm@192.168.1.41
# use it
export LEAF_SSH_OPTS="-i ~/.ssh/leaf_node_key"
```

### 7.11 `authorized_keys` command restriction

The strictest posture: the cluster key is allowed to run **only** `leaf task start`:

```
command="leaf task start ${SSH_ORIGINAL_COMMAND#* }",\
  no-port-forwarding,no-X11-forwarding,\
  no-agent-forwarding,no-pty \
  ssh-ed25519 AAAA... leaf-cluster
```

With this in place, a compromised master key can submit and start tasks. It
cannot open a shell, run arbitrary commands, or copy arbitrary files.

`leaf node install-key` (planned) generates this line automatically and appends
it to the worker's `authorized_keys`.

### 7.12 Per-node non-root user

```bash
# on each worker
useradd -m -s /bin/bash leafrunner
passwd -l leafrunner          # disable password login
su - leafrunner -c "leaf node init --node-id $(hostname)"
# install cluster key for this user only
su - leafrunner -c "mkdir -p ~/.ssh; cat >> ~/.ssh/authorized_keys" \
	< ~/.ssh/leaf_node_key.pub
```

The `leafrunner` user owns `~leafrunner/.leaf` and the `leaf` binary path. No
other filesystem access is granted.

### 7.13 LAN-only SSH via firewall

```bash
# ufw (Ubuntu)
ufw allow from 192.168.1.0/24 to any port 22
ufw deny 22

# nftables
nft add rule inet filter input \
	ip saddr 192.168.1.0/24 tcp dport 22 accept
nft add rule inet filter input tcp dport 22 drop
```

Combined with a dedicated key and command restriction, this means:
- Only LAN-origin connections accepted
- Only the cluster key accepted
- Only `leaf task start` executable via that key

---

## 8. The 60% Stop Point — Three Directions

The active discovery layer (`leaf nodes scan`) and the registry (`nodes.json`)
are implemented and working. The next decision is **how nodes make themselves
known without being asked**.

### Direction A — UDP Beacon (stdlib, zero dependencies)

Implement `leaf node beacon` (node side) and `leaf nodes listen` (master side)
using raw `SOCK_DGRAM` with `SO_BROADCAST`. Beacon packets are JSONL. The master
collects beacons for N seconds, verifies each with an SSH probe, then optionally
registers.

- **Complexity:** low — ~120 lines of Python, two new commands
- **Dependencies:** none beyond stdlib
- **Works across:** same broadcast domain only (no routed subnets)
- **Security:** beacons are unauthenticated; SSH probe step verifies
- **Best for:** home lab, single /24, developer workstations

### Direction B — mDNS via `avahi-browse` / system daemon

Use the system's existing mDNS stack. On Linux, `avahi-browse -t -r _leaf._tcp`
gives a list of advertised services. On macOS, `dns-sd -B _leaf._tcp local`.
`leaf node advertise` calls `avahi-publish-service` (Linux) or `dns-sd -R`
(macOS) to register. The master browses with `avahi-browse`.

- **Complexity:** medium — shell wrappers around system tools, platform branching
- **Dependencies:** `avahi-daemon` (Linux), built-in on macOS — no pip
- **Works across:** single link-local domain (same as broadcast)
- **Security:** DNS-SD records are unauthenticated; SSH probe step verifies
- **Best for:** mixed macOS/Linux LAN, teams already using Bonjour/Avahi

### Direction C — SSH Config file generation (`~/.ssh/config` + `known_hosts`)

Skip passive discovery entirely. Instead, make the active scan **persist its
results into `~/.ssh/config`** so that `ssh leaf-gpu1` works without leaf at
all. Each discovered node gets a `Host leaf-NODEID` block with `HostName`,
`User`, `IdentityFile`, `ProxyJump` if applicable, and `StrictHostKeyChecking no`
scoped to the cluster subnet.

```
Host leaf-gpu-node-01
	HostName 192.168.1.41
	User sm
	IdentityFile ~/.ssh/leaf_node_key
	StrictHostKeyChecking accept-new
```

- **Complexity:** low — generate + write SSH config blocks, no new protocol
- **Dependencies:** none
- **Works across:** any network the master can reach by SSH (including jump hosts)
- **Security:** strongest — leverages SSH's own known_hosts verification
- **Best for:** teams that use standard SSH tooling alongside leaf; makes `leaf`
  nodes first-class SSH hosts visible to all tools

---

*Implementation continues from this point after direction is selected.*
