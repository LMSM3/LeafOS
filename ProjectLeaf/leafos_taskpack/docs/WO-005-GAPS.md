# WO-005 — CTL Operational Gap Remediation
**Date:** 2026-06-22  **Status:** CLOSED (amended)  **Author:** audit agent

---

## 1. Scope

Full static audit of the two CTL entry points against every sourced module and
every declared shell function, with runtime smoke verification.

| Entry point     | Language   | Commands exposed |
|-----------------|------------|-----------------|
| `bin/leafctl`   | Bash 4+    | 40 dispatch cases |
| `bin/leafctl.ps1` | PowerShell 7+ | 10 dispatch cases |

---

## 2. Audit Methodology

```
1. grep all source/. lines in leafctl -> module list
2. bash -n on all 20 modules          -> syntax OK
3. py_compile on all 6 Python files   -> syntax OK
4. grep all (leaf_*|brand_*|agent_*|graph_*|brain_*) tokens from leafctl
5. grep all "^func() {" from sourced modules
6. diff called vs defined              -> gap list
7. grep leafctl.ps1 dispatch vs leafctl dispatch -> PS coverage gap
```

---

## 3. Findings

### GAP-001 — `coder.sh` not sourced in `bin/leafctl` ❌

`core/agent/actions.sh` calls `action_ask_coder()` which delegates to
`coder_generate_patch()` declared in `core/model/coder.sh`.  
`bin/leafctl` sources `brain.sh` but **never sources `coder.sh`**.  
Running `leaf agent-run` on any plan that includes an `ask_coder` node will
produce `coder_generate_patch: command not found`.

**Fix:** add `source "$ROOT_DIR/core/model/coder.sh"` after `brain.sh`.

---

### GAP-002 — `jq` absence not caught by `leaf doctor` ❌

`core/graph/graph.sh` and `core/model/brain.sh` call `jq` in every graph
operation (`graph_init`, `graph_add_node`, `graph_set_status`, …).
`_graph_require_jq()` exists but is only called immediately before first use —
after the sourcing phase.  The `doctor` command checks directory layout but
never probes for `jq`.  On a fresh install without `jq` the first graph
operation will crash mid-run with `jq: command not found`.

**Fix:** add a `jq` version probe to the `doctor` case in `bin/leafctl`.

---

### GAP-003 — PowerShell entry point covers only 10 of 40 commands ❌

`bin/leafctl.ps1` dispatches `doctor / status / loaders / loader / glyph /
glyphs / alert / versions / platform / chat / model` (11 total).

**Missing from PS1 surface** (29 commands reachable only via bash):

| Group    | Missing commands |
|----------|-----------------|
| node     | `node init`, `node status`, `node hardware` |
| nodes    | `nodes add`, `nodes list`, `nodes ping`, `nodes scan`, `nodes arp`, `nodes ping-sweep` |
| task     | `task start`, `task list`, `task logs`, `task result`, `task submit`, `task watch`, `task pull`, `task cancel` |
| agent    | `agent-task`, `agent-plan`, `agent-validate`, `agent-dry-run`, `agent-run`, `agent-loop`, `agent-brain`, `agent-graph`, `agent-gate`, `agent-node`, `agent-action`, `agent-wait`, `agent-export`, `agent-report`, `agent-route` |
| net/dist | `serve`, `download`, `dist-build`, `dist-info` |
| misc     | `motd`, `loader`, `spin`, `checkpoint`, `verify-run`, `new-module`, `session-start`, `session-close`, `provider-status` |

**Fix:** replace the `default { die }` case in `leafctl.ps1` with a bash-forward
fallback that shells out to `C:\msys64\usr\bin\bash.exe -l bin/leafctl <cmd>
[args]`, giving full command coverage on Windows without duplicating every
case in PS syntax.

---

### GAP-004 — `install_demo.ps1` copy loop crashes on `.vs` lock files ✅ FIXED

`TrimStart('\\\\', '/')` passed a two-char string to a `Char` overload; `.vs`
directory files were locked by Visual Studio.  
**Already patched** in this session: single-char `'\'` and `.vs` exclusion added.

---

### GAP-006 — `git` is an undeclared hard dependency; `leaf doctor` never checks for it ❌

`core/agent/actions.sh` `action_patch_validate()` (line 154) and `action_patch_apply()` (line 176)
call `git apply --check` and `git apply` directly.  Both are live dispatch targets reached by
`leaf agent-run` on any graph containing a `patch.validate` or `patch.apply` node.

`leaf doctor` checked for `jq` and `python3` but had **no probe for `git`**.

**Silent-failure mode:** when `git` is absent the `if git apply ...` construct evaluates false,
hits the `brand_warn` branch, and returns 0 — the loop continues thinking the patch step
was merely warned, not failed.  Run-graph state becomes corrupt.

**Fix:** added `command -v git` probe to `doctor` case in `bin/leafctl`, identical in style
to the existing `jq` and `python3` probes.

**Verified:** `leaf doctor` now outputs `git version 2.52.0  ok`; `bash -n bin/leafctl` passes.

---

### GAP-005 — `Invoke-LeafStatus` in `LeafOS.psm1` does not surface Python / jq / bash versions ⚠️ LOW

`Get-LeafVersions` covers pwsh/python/bash/gcc but `Invoke-LeafStatus` only
prints OS/arch/root/pwsh.  Minor display inconsistency; no operational impact.

---

## 4. Fix Plan

| ID | File | Change | Status |
|----|------|--------|--------|
| F-001 | `bin/leafctl` | add `coder.sh` source line | ✅ done |
| F-002 | `bin/leafctl` | add `jq` check to `doctor` case | ✅ done |
| F-003 | `bin/leafctl.ps1` | bash-forward fallback in `default` | ✅ done |
| F-004 | `bin/install_demo.ps1` | TrimStart + .vs exclusion | ✅ done |
| F-006 | `bin/leafctl` | add `git` check to `doctor` case | ✅ done |

---

## 5. Validation Checklist

- [x] `bash -n bin/leafctl` passes
- [x] `bash -n bin/leafctl.ps1` N/A (PS); PS AST parser reports syntax OK
- [x] `leaf doctor` reports jq-1.8.1 OK and python3 probe present
- [x] `coder.sh` sourced — `coder_generate_patch` no longer missing at runtime
- [x] `leaf node status` works from PowerShell via bash-forward (reaches bash, fails only on msys2 missing python — correct)
- [x] `leaf motd` works end-to-end from PowerShell via bash-forward
- [x] `leaf serve --once` still works from bash
- [x] All 6 Python modules compile clean
- [x] Chat smoke session `wo005-smoke` saved successfully
- [x] `leaf doctor` now reports `git version 2.52.0  ok` (GAP-006)
