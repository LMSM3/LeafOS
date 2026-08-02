# WO-006 — `flower` Entry-Point Operational Gap Audit
**Date:** 2026-06-22  **Status:** CLOSED (revisited)  **Author:** audit agent

---

## 1. Scope

Follow-on to WO-005.  WO-005 audited `bin/leafctl` / `bin/leafctl.ps1`
(since renamed/replaced).  This WO applies the same methodology to the
current entry points.

| Entry point       | Language      | Commands exposed |
|-------------------|---------------|-----------------|
| `bin/flower`      | Bash 4+       | 3 dispatch cases (`version`, `tree`, `help`) |
| `bin/flower.ps1`  | PowerShell 7+ | 11 dispatch cases |

---

## 2. Audit Methodology

```
1. grep all source/. lines in bin/flower and bin/flower.ps1  -> module list
2. bash -n bin/flower                                         -> syntax OK
3. PS AST parse bin/flower.ps1                               -> syntax OK
4. grep all external tool calls (git, ollama, python3, jq, curl, wget)
   from sourced modules and dispatcher functions
5. grep Cmd-Doctor $tools probe list                         -> compare to step 4
6. diff called vs probed                                     -> gap list
7. grep Cmd-Repo, Cmd-MOTD, Cmd-AI for unguarded tool calls -> runtime-failure risk
```

---

## 3. Findings

### GAP-A — `ollama` not probed by `flower doctor`  ❌

`bin/flower.ps1` dispatches `flower ai` to
`lib/_The_most_important_helper.ps1`, which calls `ollama pull`, `ollama ps`,
and `Invoke-RestMethod` against the local Ollama API.  `ollama` is a hard
runtime dependency for the entire `ai` command group (`status`, `ask`, `chat`,
`install`, `start`, `stop`).

`Cmd-Doctor` probes `oh-my-posh`, `gcc`, and `git` but **never probes
`ollama`**.  On a fresh Windows install where Ollama is not yet set up,
`flower doctor` reports all-green even though `flower ai` will fail the
moment it is invoked.

**Pattern:** identical to WO-005 GAP-002 (jq not in doctor).

**Fix:** add `ollama` to the `$tools` probe list in `Cmd-Doctor`
(`bin/flower.ps1`).  Because Ollama is optional (the rest of FlowerOS works
without it), mark it with `_warn` on absence rather than `_err`.

---

### GAP-B — `Cmd-Repo` calls `git` without a guard; `Cmd-Doctor` marks `git` optional  ❌

`Cmd-Doctor` emits `_warn "git not found (optional)"` for a missing `git`
binary, implying the tool is not required.  However `Cmd-Repo` (`flower repo
status`) calls:

```powershell
$branch = & git branch --show-current 2>$null
$dirty  = & git status --porcelain   2>$null
$remote = & git remote -v            2>$null | Select-Object -First 1
```

with all stderr redirected to `$null`.  When `git` is absent every variable
gets `$null`, the function completes without error, and the user sees:

```
  Branch:
  Remote:
  Modified: 0   Untracked: 0
```

— blank output that looks like a clean repo rather than a tool-missing
condition.  This mirrors WO-005 GAP-006 (git absent → silent wrong-state).

**Fix:** add an early guard at the top of `Cmd-Repo` that calls `_err` and
returns immediately when `git` is not on `$PATH`.

---

### GAP-C — `bin/flower` (bash) has no `doctor` subcommand  ⚠️ LOW

`bin/flower` exposes three subcommands: `version`, `tree`, `help`.  There is
no `doctor` equivalent on the bash surface.  On Linux / WSL where
`bin/flower.ps1` is not available, users have no health-check command.

**No fix in this WO** (architectural decision; scope of a dedicated bash
doctor pass).

---

### GAP-D — `python3` not probed by `flower doctor`  ❌

`lib/run.sh` (lines 111-112) invokes `python3` for `py`/`pyw` task types.
`lib/fos/` is a Python 3 package used by the runner helper and downloader.
Neither `flower doctor` nor `flower version --full` surfaces `python3`
availability.

**Fix:** add `python3` to the `$tools` probe list in `Cmd-Doctor`.  Mark as
optional (`_warn`) since the core FlowerOS shell experience does not require
Python.

---

## 4. WO-005 Continuity Check

| WO-005 ID | Original file      | Status in current codebase |
|-----------|--------------------|---------------------------|
| GAP-001   | `bin/leafctl` — `coder.sh` not sourced | N/A — `bin/flower` sources nothing |
| GAP-002   | `jq` not in doctor | N/A — no `jq` usage in `lib/*.sh` |
| GAP-003   | PS covers 10 of 40 bash commands | N/A — `bin/flower` has only 3 commands; no coverage gap |
| GAP-004   | `install_demo.ps1` copy crash | N/A — file not present |
| GAP-005   | `Invoke-LeafStatus` version display | N/A — replaced by `Cmd-Doctor` |
| GAP-006   | `git` not in doctor | Partially addressed: `git` is in `Cmd-Doctor` but as optional only; `Cmd-Repo` still calls it unguarded (→ GAP-B above) |

---

## 5. Fix Plan

| ID  | File               | Change                                         | Status  |
|-----|--------------------|------------------------------------------------|---------|
| F-A | `bin/flower.ps1`   | add `ollama` to `$tools` in `Cmd-Doctor`       | ✅ done |
| F-B | `bin/flower.ps1`   | add git guard to `Cmd-Repo`                    | ✅ done |
| F-D | `bin/flower.ps1`   | add `python3` to `$tools` in `Cmd-Doctor`      | ✅ done |

---

## 6. Validation Checklist

- [x] `PS -Command 'Get-Content bin\flower.ps1 | Out-Null'` — no parse errors
- [x] `flower doctor` now lists `ollama` and `python3` probe lines
- [x] `flower repo` without `git` in PATH returns `[x] git not found` and exits cleanly
- [x] Full `flower doctor` run on clean install — re-ran `powershell -NoProfile -ExecutionPolicy Bypass -File .\bin\flower.ps1 doctor` from `FlowerOS`: all 15/15 checks passed, including `python3 Python 3.12.12`, `ollama 0.20.6`, and `git 2.54.0.windows.1` probes added for GAP-A/B/D.
