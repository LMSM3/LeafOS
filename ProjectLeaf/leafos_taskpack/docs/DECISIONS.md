# LeafOS — Decision Log

> Every significant design or implementation choice, recorded at the moment it
> was made. This is not a changelog. It is a rationale ledger: what was decided,
> why, and what was explicitly rejected.

---

## DEC-001 — Python stdlib only; no pip on the critical path

**Date:** 2026-06-21  
**Affects:** `core/node/leaf_node.py`, `core/net/discover.py`

**Decision:** Every module in `core/` that runs on a node must import only the
Python standard library. No `pip install` steps are allowed as a prerequisite
for basic functionality.

**Reasoning:** Nodes are arbitrary machines on a LAN. They may be minimal Linux
installs, Windows boxes, or locked-down corporate machines. Any dependency that
requires a package manager introduces a failure mode outside the project's
control. Python 3.8+ is already required; everything it ships with is fair game.

**Rejected alternatives:**
- `zeroconf` (mDNS library) — would be the right tool for passive discovery but
  breaks the stdlib rule. Deferred to a future optional plugin layer.
- `paramiko` (pure-Python SSH) — would remove the hard `ssh` binary dependency
  but adds a 3 MB compiled wheel and its own key-format opinions. Not worth it.
- `psutil` (hardware probing) — nicer API than `sysconf`/`ctypes`, but adds a
  pip dep. The ctypes + sysconf approach is 40 extra lines and zero deps.

---

## DEC-002 — `ThreadPoolExecutor` for concurrent SSH probes, not `asyncio`

**Date:** 2026-06-21  
**Affects:** `core/net/discover.py` — `subnet_scan()`, `ping_filter()`

**Decision:** Use `concurrent.futures.ThreadPoolExecutor` for all concurrent
I/O in the discovery engine.

**Reasoning:** The work is I/O-bound (`ssh` subprocess launch + wait).
`ThreadPoolExecutor` is synchronous at the call site, debuggable with regular
stack traces, requires no event-loop setup, and is available from Python 3.2.
`asyncio.subprocess` would require restructuring every call site to be a
coroutine and adds measurable complexity for zero throughput gain on a /24 scan
(254 hosts, 3 s timeout, ~40 s total).

**Rejected:** `asyncio.gather` with `asyncio.subprocess` — correct approach for
a standalone async program; wrong fit for a synchronous shell tool that is
invoked once and exits.

---

## DEC-003 — SSH probe is the authoritative leaf-node check; ping/ARP are pre-filters only

**Date:** 2026-06-21  
**Affects:** `core/net/discover.py` — scan pipeline

**Decision:** A host is confirmed as a Leaf node only when it returns valid JSON
from `leaf node status --json` over SSH. ICMP ping (`--ping-first`) and ARP
table reads (`--arp`) are optional pre-filters that reduce the probe set; they
are never the final answer.

**Reasoning:**
- Ping can be blocked by host firewalls while SSH is open.
- ARP entries can be stale (default TTL is 20 minutes on Linux).
- A machine that responds to ping is not necessarily a Leaf node.
- The SSH probe is the only test that proves all three conditions simultaneously:
  machine is up, SSH is reachable, Leaf is installed and initialized.

**Consequence:** `--ping-first` and `--arp` are additive opt-in flags, not
defaults. On a home /24 with 32 concurrent probes and a 3 s timeout, the full
scan completes in under 40 s without any pre-filter. Pre-filters only matter
for large subnets (/16+) or slow links.

---

## DEC-004 — Pre-filters are optional flags, not a mandatory pipeline

**Date:** 2026-06-21  
**Affects:** `core/net/discover.py` CLI, `docs/LAN_ACCESS.md` Section 3

**Decision:** The three-stage filter pipeline (ping → ARP → SSH) is
opt-in. The default `leaf nodes scan SUBNET` runs only the SSH probe.

**Reasoning:** The target use case is a home lab or small office LAN with
20–50 live hosts. The SSH probe across 254 IPs with 32-worker concurrency
completes fast enough that the pre-filters provide no perceptible speedup.
Making them mandatory would add subprocess calls (`ping`, `arp`) that may not
exist on all platforms (e.g. minimal containers). Optional is always safer than
mandatory for utility functions.

---

## DEC-005 — `discover.py` calls `leaf_node.py registry-add` for auto-registration, not direct JSON write

**Date:** 2026-06-21  
**Affects:** `core/net/discover.py` — `_register_node()`, `auto_register()`

**Decision:** When `--register` is passed, discovered nodes are added by
spawning `python3 leaf_node.py registry-add` as a subprocess, not by writing
`nodes.json` directly.

**Reasoning:** `leaf_node.py` is the single source of truth for the registry
schema, the atomic write pattern (write-then-move), and the dedup logic.
Duplicating that logic in `discover.py` would create two codepaths that could
diverge. The subprocess call costs ~50 ms per registration but registration
happens once, not in the scan hot path.

**Alternative considered:** Importing `leaf_node` as a Python module. Rejected
because `leaf_node.py` is designed to be called as a script (it runs
`_force_utf8_streams()` at import time, has a `main()` entry point). Treating
it as an importable module would require restructuring it into a proper package.
That refactor is planned for 0.7.0 (`core/node/` as a Python package with
`__init__.py`).

---

## DEC-006 — `LEAF_SSH_OPTS` is inherited by `discover.py` from the environment

**Date:** 2026-06-21  
**Affects:** `core/net/discover.py` — `subnet_scan()`, `--ssh-opts` argument

**Decision:** If `--ssh-opts` is not explicitly passed to `leaf nodes scan`,
`discover.py` reads `$LEAF_SSH_OPTS` from the environment and applies it to
every SSH probe.

**Reasoning:** A user who has already configured `export LEAF_SSH_OPTS="-i
~/.ssh/leaf_node_key"` for `leaf task submit` expects that key to be used
automatically during scanning. Requiring a separate `--ssh-opts` flag for scans
would force them to repeat themselves. Environment variables are the correct
mechanism for cross-command configuration in a shell tool.

**Security note:** The LEAF_SSH_OPTS string is split by whitespace and passed
as a list to `subprocess.run`. It is not passed through a shell. Shell injection
via a crafted `LEAF_SSH_OPTS` value is therefore not possible.

---

## DEC-007 — Auto-registration names nodes by `node_id`; deduplicates by appending IP octet

**Date:** 2026-06-21  
**Affects:** `core/net/discover.py` — `auto_register()`

**Decision:** When `--register` is used, the registry name for a discovered
node is taken from the `node_id` field in its `leaf node status --json`
response. If two nodes share the same `node_id`, the last IP octet is appended
as a suffix (`gpu-node-01-42`).

**Reasoning:** `node_id` is the human-meaningful name the operator chose when
they ran `leaf node init --node-id`. Using it as the registry key preserves
that intention. The IP-suffix dedup is an edge case (two nodes with identical
`node_id` values) that must not silently overwrite an existing entry.

**Rejected:** Using the IP address as the name (e.g. `node-192-168-1-41`).
This is stable but opaque — you lose the operator's chosen name. Using
the hostname is also valid but some machines have identical default hostnames
(e.g. `raspberrypi`).

---

## DEC-008 — Direction C selected for passive discovery: SSH config generation

**Date:** 2026-06-21  
**Affects:** Next implementation milestone

**Decision:** Of the three passive-discovery directions presented at the 60%
stop point, **Direction C — SSH config file generation** is selected.

**The three options were:**
- **A — UDP Beacon:** `leaf node beacon` broadcasts JSONL on `SO_BROADCAST`;
  `leaf nodes listen` collects for N seconds and SSH-verifies. Stdlib, ~120
  lines. Works only on one broadcast domain.
- **B — mDNS via system daemon:** delegates to `avahi-browse`/`dns-sd`.
  Platform-branching heavy; requires avahi-daemon on Linux.
- **C — SSH config generation:** scan results are written into `~/.ssh/config`
  as `Host leaf-NODEID` blocks. No new protocol, no daemon, strongest security.

**Why C wins:**
1. **Zero new protocol surface.** No UDP port, no daemon, no multicast group.
2. **Every SSH tool benefits automatically.** VS Code Remote, `rsync`, `scp`,
   `ansible`, and `mosh` all read `~/.ssh/config`. Once `leaf nodes scan
   --write-ssh-config` runs, `ssh leaf-gpu1` works without `leaf` involved.
3. **Works across any topology SSH can reach**, including jump-host proxied
   nodes — Direction A is limited to one broadcast domain.
4. **Strongest security.** SSH's `StrictHostKeyChecking accept-new` and
   `known_hosts` verification are inherited. There is no unauthenticated beacon
   packet to spoof.
5. **Simplest implementation.** Write formatted text blocks to a file. No
   socket programming, no timing, no retransmit logic.

**What is deferred:**
- Direction A (UDP beacon) remains a valid future addition for the "nodes
  announce themselves without being scanned" use case. It will be a separate
  opt-in flag, not the primary mechanism.
- Direction B (mDNS) may be added as a thin wrapper around system tools in a
  platform-specific optional module.

---

## DEC-009 — `leaf dashboard` is the canonical product status UI

**Date:** 2026-06-21  
**Affects:** `core/ui/dashboard.py`, `bin/leafctl`

**Decision:** A standalone Python dashboard (`core/ui/dashboard.py`) is the
primary read-only status surface for the full Leaf system. It reads all data
directly from files (no subprocess calls for status reads) and renders a
two-column ANSI layout in any terminal.

**Design constraints:**
- No curses (not portable to Windows without extra setup)
- No subprocess calls for data reads (fast, no SSH latency on open)
- ARP table read is the only exception (one subprocess to `arp` or direct
  `/proc/net/arp` read — milliseconds)
- Colors match `brand.sh` exactly (same ANSI escape codes)
- `--watch N` for live refresh; `--json` for scripting; `--no-color` for pipes
- Works at 80 columns minimum; responsive up to 200 columns

**Data sources:**
- `$LEAF_HOME/node.json` → node identity panel
- `$LEAF_HOME/{inbox,queued,running,done,failed}/` → task queue counts
- `$LEAF_HOME/nodes.json` → cluster registry panel
- `$LEAF_HOME/logs/*.jsonl` (last modified first) → recent events panel
- `/proc/net/arp` or `arp -n` → LAN ARP panel
- Hardware: read from `node.json` if cached; otherwise live `probe_hardware()`

---

## DEC-010 — Task state directory counts are the queue; no separate queue file

**Date:** 2026-06-21 (confirmed, not changed)  
**Affects:** `core/node/leaf_node.py`, `core/ui/dashboard.py`

**Decision:** The number of `.json` files in each state directory (`inbox/`,
`queued/`, `running/`, `done/`, `failed/`) is the queue state. There is no
separate queue metadata file.

**Reasoning:** File counts are atomic from the OS perspective: a `shutil.move`
is atomic on POSIX for same-filesystem moves. No separate queue file means no
possibility of the file and the directory state diverging due to a crash. The
dashboard reads counts with `len(os.listdir())` — O(n) but n is small (home lab
scale) and involves no lock.

**Implication for the dashboard:** Counts are always exact; there is no "last
known" stale count to expire or refresh.

---

## DEC-011 - The version-2 inlet is the single project execution authority

**Date:** 2026-07-21  
**Affects:** `core/python/leaf_loop_inlet.py`, `core/python/leaf_agent_loop.py`, `core/python/leaf_live_project.py`

**Decision:** Project instructions from CLI, TUI, JSON task, or work order must
normalize into one persistent version-2 run and queue. Provider output is a
proposal. Path policy, approval, execution, validation, repair, checkpoint,
and report remain CPU-authoritative.

**Reason:** Multiple queues or direct renderer/provider mutation would make
resume, recovery, priority, audit, and safety disagree. One inlet gives every
surface the same durable behavior.

---

## DEC-012 - Resident scheduling wraps the inlet instead of replacing it

**Date:** 2026-07-21  
**Affects:** `core/python/leaf_resident_supervisor.py`, `core/python/leaf_resource_governor.py`

**Decision:** One separately leased supervisor evaluates foreground and
hardware pressure, maintains worker availability, and admits at most one
evidence-derived next improvement at a time. It cannot expand the approved
project, command, mutation, failure, or change boundary.

**Reason:** Continual work needs lifecycle ownership and resource adaptation,
but those concerns must not create a second executor or unbounded autonomy.

---

## DEC-013 - The TUI is canonical for agent runs; dashboard remains node-specific

**Date:** 2026-07-21  
**Affects:** `core/ui/tui/`, `core/tui/`, `core/ui/dashboard.py`

**Decision:** Python and native TUI renderers consume one normalized read-only
snapshot and send authenticated named inlet controls. `q` closes only the
window. The older dashboard remains the optional SSH node/cluster status
surface and does not control resident runs.

**Reason:** The agent loop requires task dependencies, provider progress,
resource decisions, validation, checkpoints, and reconnect cursors that are
not represented by the node dashboard's directory-count model.

---

## DEC-014 - Medium MoE candidates replace GLM-5.2 as the local research direction

**Date:** 2026-07-21  
**Affects:** `config/medium_moe_policy.json`, `core/python/leaf_moe_contract.py`, `core/python/leaf_overnight.py`, provider defaults

**Decision:** GLM-5.2 is deprecated for local operation on the reference 12 GB RTX 4070 and 48 GB RAM host. New research targets operator-selected MoE candidates with 47-156 billion total parameters. Candidate identity, active topology, quantization, local artifact, thresholds, placement, and measured 4/8/64 minute evidence are required before promotion. The incumbent Vulkan route remains active until a candidate qualifies, and promotion always requires operator approval.

**Reason:** Operator experimentation and theory favor medium sparse models over one model too large for the machine. Repository measurements establish that offload shape and workstation headroom matter, but do not yet prove that an unspecified model in the new range will fit. The contract therefore separates the operator decision, historical proposals, and measured facts.

**Storage boundary:** Current SSD behavior is llama.cpp mmap plus the operating-system page cache. LeafOS does not yet implement managed expert streaming or SSD/RAM/VRAM tier placement, so the policy records that capability as false.
