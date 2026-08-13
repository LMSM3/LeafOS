# WO-050-R2 — Indicator Shell Compatibility Repair

## Identity

- Parent: [WO-050-R1](WO-050-R1-pack-glyph-subsystem-evidence-repair.md)
- Repair date: 2026-08-11
- Scope: PowerShell 5/5.1/7, Git Bash/MSYS2, WSL interop, host diagnosis
- Release target: LeafOS 0.2.2

## Repair statement

The subsystem indicator is only dependable when it survives the common host
mistakes surrounding it. This repair preserves one glyph/evidence implementation
while adding compatible prompt execution, version-probed host discovery, Unix to
Windows path translation, and a doctor report that distinguishes installation,
policy, location, integrity, dependency, and wrong-host failures from code bugs.

## Acceptance criteria

- [x] Keep prompt activation in the caller's process.
- [x] Make the indicator module parse and execute in Windows PowerShell 5.1 and PowerShell 7.
- [x] Avoid PowerShell 7-only null-coalescing, escape, and file-overwrite APIs in that path.
- [x] Prefer PowerShell 7 for general commands while allowing PowerShell 5+ for the compatible indicator.
- [x] Reject a detected PowerShell 5/5.1 host before forwarding a PowerShell-7-only general command.
- [x] Version-probe PATH, known-location, Store-alias, and Windows-interop candidates.
- [x] Translate WSL/MSYS script paths before Windows executable dispatch.
- [x] Add `indicator doctor` with host, policy, root, parser, module, and pack-registry evidence.
- [x] Publish a reusable shell compatibility and user-error triage procedure.
- [ ] Complete independent qualification on more than ten people's computers.

## Evidence boundary

Local runtime tests establish compatibility on the available machine; they do
not establish the outstanding multi-person qualification item. PowerShell 5.0
is maintained as the syntax/API floor but is not installed locally, so its live
result remains a matrix item rather than a completed claim.

## Status

[W] WO-050-R2: indicator shell compatibility repair
[D] Retroactive Day 2 close: resilient host selection and installation diagnosis
[I] DONE: local indicator and capability-specific shell-routing implementation
[V] PASS: 46 focused canonical-tree tests, dual-host parsing, native 5.1/7 smokes, and MSYS-to-PowerShell 7 doctor routing
[P] LOCAL: implementation reconciled into canonical `C:\R\LeafOS0.2.2`; no staging, commit, or publication performed
[N] STOP: no new WO opened; the independent 11+ host matrix remains a deferred release gate

## Evidence log

- 2026-08-11: Windows PowerShell 5.1 and PowerShell 7.6.4 parsed every touched
  PowerShell file; Bash parsed the resolver and dispatcher files.
- 2026-08-11: 23 focused indicator tests passed, including Windows PowerShell
  prompt activation, Ficus glyph rendering, active leaf fallback, host resolution,
  missing/corrupted install diagnosis, and existing evidence behavior.
- 2026-08-11: 3 focused Git Bash/MSYS2 dispatch tests passed for help, Ficus
  glyph resolution, and the doctor report.
- 2026-08-11: the root WSL command reached Windows PowerShell 7.6.4 through
  translated interop, preserved the UTF-8 pack glyph, reported route
  `wsl-windows-interop`, and returned `ready`.
- 2026-08-11: an adversarial WSL run removed PowerShell 7 and the Store alias
  from discovery; the launcher fell back to Windows PowerShell 5.1, returned
  `ready`, and preserved the Ficus `identity.symbol` glyph.
- 2026-08-11: the same adversarial WSL environment exposed a general-forwarding
  defect: `home` sent the PowerShell-7-only dispatcher to Windows PowerShell 5.1
  and produced parser errors. The shared detector now exposes a caller-specific
  version predicate; general forwarding requires 7.0 while indicator dispatch
  requires 5.0.
- 2026-08-11: the forced WSL 5.1 general route now exits nonzero with one exact
  PowerShell 7 repair and no parser output. All 15 Bash-dispatch tests and all
  23 indicator tests passed after the correction.
- 2026-08-11: no PowerShell 5.0 executable or independent-machine cohort was
  available; neither result is claimed.
- 2026-08-13: canonical reconciliation passed 46 focused tests, Bash and Python
  syntax checks, PowerShell 5.1 and 7 parsing, a Windows PowerShell 5.1 doctor,
  a PowerShell 7 Ficus preview, and an MSYS-to-PowerShell 7 doctor round trip.
  The independent 11+ host qualification remains deferred and unclaimed.
