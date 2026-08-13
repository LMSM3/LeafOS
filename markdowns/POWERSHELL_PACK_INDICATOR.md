# PowerShell Pack Indicator and Quiet Subsystems

LeafOS places one small living glyph in the PowerShell prompt while a LeafOS
subsystem is active. The glyph is an evidence projection, not decoration:

- active subsystem plus a resolved pack identity -> that pack's exact
  `identity.symbol`;
- active subsystem without a resolved pack identity -> the canonical
  `leaf.active` glyph (`🍃`);
- no active subsystem -> no LeafOS prompt glyph.

The accompanying `leafos.subsystem_indicator_evidence.v1` object records the
live process source, subsystem name, process ID, evidence grade, selected pack,
and exact claims. A visible production-grade pack glyph therefore evidences
both `subsystem.process.active` and `pack.identity.bound`.

That is a bounded claim. It does not by itself prove that every pack weight is
resident, that a provider health probe passed, or that a capability was
authorized. Those facts retain their own evidence gates.

## Enable the prompt indicator

Importing a module from a child script cannot change its parent's prompt, so
the prompt hook must run inside the current PowerShell session:

```powershell
. "$PWD\PowerShell-Version\Enable-LeafPackIndicator.ps1"
```

This prompt path supports Windows PowerShell 5/5.1 and PowerShell 7+. Run a
host/install diagnostic before enabling it when the shell location is uncertain:

```powershell
.\leafos.ps1 indicator doctor
.\leafos.ps1 indicator doctor --json
```

Git Bash, MSYS2, and WSL use the Bash launcher, which version-probes native and
Windows-interoperable PowerShell candidates and translates the script path when
needed. General LeafOS commands still prefer PowerShell 7; the indicator can use
5/5.1 because its module is deliberately compatible and must remain in the
current prompt process. The reusable diagnosis policy is documented in
[`procedures/SHELL-COMPATIBILITY-AND-USER-ERROR-TRIAGE.md`](../procedures/SHELL-COMPATIBILITY-AND-USER-ERROR-TRIAGE.md).

To enable it in future sessions, put that line in `$PROFILE`. LeafOS does not
edit the profile automatically. The equivalent expanded form is:

```powershell
Import-Module "$PWD\ProjectLeaf\leafos_taskpack\core\powershell\LeafOS.psm1"
Enable-LeafPackIndicator
```

Select a pack persistently, inspect the result, or clear the selection:

```powershell
.\leafos.ps1 indicator preview ficus
.\leafos.ps1 indicator set ficus
.\leafos.ps1 indicator status
.\leafos.ps1 indicator clear
```

`indicator status --json` returns the typed evidence object under `evidence`.
The prompt will begin or stop showing the glyph as the owned subsystem process
appears or exits; pack selection alone does not force an active state.

Within an imported session, `Set-LeafActivePack ficus` changes only the current
session unless `-Persist` is supplied. `Disable-LeafPackIndicator` restores the
prompt function that existed before LeafOS was enabled.

ASCII and colour controls remain independent:

```powershell
$env:LEAF_GLYPHS = 'ascii' # [pack:ficus] or (live)
$env:NO_COLOR = '1'        # keep the glyph, remove ANSI colour
```

## How the pack is inferred

The first declared source wins:

1. `-Pack` passed directly to the indicator function;
2. `LEAF_ACTIVE_PACK` in the environment;
3. a pack selected in the current module session;
4. `runs/active-pack.json`, written by `indicator set` or `-Persist`;
5. pack metadata in the active run's `run.json`;
6. a future `leafos_runtime.defaults.active_pack` value;
7. no pack: use `leaf.active` while a subsystem is active.

A higher-priority source that names a missing or malformed manifest is reported
as unresolved instead of being silently replaced by a lower-priority choice.
LeafOS does not fabricate an identity; it renders the leaf.

## How subsystem activity is evidenced

Production detection accepts the first live owned-process source:

1. the PID in `LEAF_SUBSYSTEM_PID`, optionally named by
   `LEAF_SUBSYSTEM_NAME`;
2. `runs/vulkan-provider/llama-server.pid` when that process is alive;
3. a live PID in the active run's `resident.lock`, `worker.lock`, or
   `active-process.json` lease.

For presentations that intentionally do not launch a provider, a demo-only
projection is explicit:

```powershell
$env:LEAF_SUBSYSTEM_ACTIVE = '1'
$env:LEAF_SUBSYSTEM_NAME = 'showcase'
. "$PWD\PowerShell-Version\Enable-LeafPackIndicator.ps1" -Pack ficus
```

This path is labeled `evidence_grade: demo` and never impersonates
process-backed evidence. Remove the variables to end it:

```powershell
Remove-Item Env:\LEAF_SUBSYSTEM_ACTIVE, Env:\LEAF_SUBSYSTEM_NAME
```

For any other owned subsystem launcher, set `LEAF_SUBSYSTEM_PID` to its live
PID before enabling the prompt hook. Stale or missing PIDs fail closed and the
glyph disappears.

## Preventing CMD-window spam

The successful Windows pattern is now a project rule: invoke the real
executable directly, suppress window creation at the process API, and preserve
output in pipes or log files. Hiding a process must never hide its evidence.

For a bounded child whose output is needed immediately:

```powershell
$result = Invoke-LeafQuietProcess `
  -FilePath (Get-Command python).Source `
  -ArgumentList @('-c', 'print("ready")') `
  -TimeoutSeconds 10

if ($result.ExitCode -ne 0) { throw $result.StdErr }
```

This uses `ProcessStartInfo` with `UseShellExecute = false`,
`CreateNoWindow = true`, separate redirected stdout/stderr, and no `cmd.exe`.

For a long-lived subsystem:

```powershell
$child = Start-LeafQuietProcess `
  -FilePath $server `
  -ArgumentList $arguments `
  -StdOutPath .\logs\provider.out.log `
  -StdErrPath .\logs\provider.err.log

$child.ProcessId
```

On Windows this uses `WindowStyle = Hidden`; stdout and stderr logs are
mandatory and distinct. The caller must also persist the PID, expose a status
command, and remove stale PID state after verifying the process is gone.

Python background workers follow the equivalent contract:

- include `CREATE_NO_WINDOW` and `STARTF_USESHOWWINDOW/SW_HIDE` on Windows;
- use `CREATE_NEW_PROCESS_GROUP` for controllable process trees;
- use `DETACHED_PROCESS` only for genuinely long-lived workers;
- set stdin to `DEVNULL` and route stdout/stderr to a log or pipe;
- call executables directly with argument arrays; avoid `shell=True` and
  `cmd.exe /c` unless a Windows shell built-in is genuinely required;
- retain PID, health, stop, and error-tail surfaces.

These controls suppress flashing consoles and repeated CMD windows. They do
not suppress errors, logs, exit codes, or operator control.
