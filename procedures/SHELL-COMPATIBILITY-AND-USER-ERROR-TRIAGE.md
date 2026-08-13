# Shell Compatibility and User-Error Triage

## Purpose

Shell failures are often caused by the host rather than the feature: the wrong
PowerShell instance, an unresolvable install path, execution policy, a missing
script or dependency, or a damaged installation. LeafOS launchers should detect
those states before calling something a product bug and should return one exact,
safe repair action for each failed check.

This is the generic pattern for regular PowerShell and shell code. The indicator
is its first concrete implementation.

## Host-routing contract

1. For state that must modify the current shell, such as a prompt function,
   remain in that process. The indicator supports Windows PowerShell 5/5.1 and
   PowerShell 7+ through one module and one evidence contract.
2. For a general LeafOS command, prefer a working PowerShell 7 host. Search the
   current process (when allowed), `PATH`, known install locations, Store aliases,
   and registered installations. Actually run a harmless version probe; finding
   a filename is not proof that the installation works.
3. In Bash, Git Bash, MSYS2, or WSL, prefer native `pwsh`, then a usable Windows
   `pwsh.exe` interop host, then Windows PowerShell 5/5.1 for explicitly
   compatible features.
4. Translate the script path with `wslpath -w` or `cygpath -w` before invoking a
   Windows executable from a Unix-shaped shell.
5. If no supported host works, fail softly with the attempted host class and an
   exact install, PATH, or location repair. Do not loop and do not hide the exit
   status.

The reusable implementations are
`PowerShell-Version/Resolve-LeafPowerShellHost.ps1` and
`ProjectLeaf/leafos_taskpack/core/system/versions.sh::leaf_detect_pwsh`.

## Triage sequence

Run these checks in order and retain their output:

1. **Actual host:** record executable, PowerShell version and edition, OS, and
   whether the route is WSL or Windows interop. Do not infer these from the
   terminal application's name.
2. **Command discovery:** inspect every `pwsh` and `powershell` candidate, not
   only the first alias on `PATH`.
3. **Install location:** resolve the LeafOS root and verify the requested script,
   module, pack registry, and paths containing spaces or OneDrive segments.
4. **Permissions and policy:** read execution-policy scopes and filesystem access.
   Never silently elevate, weaken machine policy, or use `sudo` to make a probe
   pass.
5. **Integrity:** parse the module under the actual host and use the installer
   verify action when a file is missing, truncated, or unexpectedly changed.
6. **Dependencies:** version-probe each required executable. A command name that
   resolves but cannot start counts as broken, not installed.
7. **Explicit reproduction:** invoke the smallest command with the full path to
   the intended executable and script.
8. **Fallback comparison:** run the same read-only probe in the next supported
   host. A host-specific failure is compatibility evidence, not yet proof of a
   feature defect.
9. **Classification:** call it a product bug only when the failure reproduces on
   a supported host with an intact installation, correct root, satisfied
   dependencies, and permitted execution.

Useful read-only probes:

```powershell
$PSVersionTable
Get-Command pwsh,powershell -All -ErrorAction SilentlyContinue
Get-ExecutionPolicy -List
.\leafos.ps1 indicator doctor --json
powershell.exe -NoProfile -File .\leafos.ps1 indicator doctor --json
pwsh -NoProfile -File .\leafos.ps1 indicator doctor --json
```

```bash
command -v pwsh pwsh.exe powershell powershell.exe 2>/dev/null
bash ./leafos.sh indicator doctor --json
```

If a trusted local script is blocked, an operator may use a process-scoped
diagnostic such as `powershell.exe -ExecutionPolicy Bypass ...` after inspecting
`Get-ExecutionPolicy -List`. LeafOS must not apply that bypass automatically or
change CurrentUser/LocalMachine policy.

## Symptom-to-cause map

| Symptom | Inspect first | Typical bounded repair |
|---|---|---|
| “running scripts is disabled” | `Get-ExecutionPolicy -List`, file provenance | Follow organization policy; use a trusted process-scoped diagnostic only when authorized |
| command not found | all command candidates and Store aliases | Install the supported host or repair `PATH` |
| script/module missing | resolved LeafOS root and install manifest | Run installer verification from the actual install root, then reinstall missing files |
| parser error | host major version and module integrity | Use the compatible entry point; replace a damaged file only through verified install media |
| dependency missing | executable path plus a harmless version probe | Install the named dependency and rerun doctor |
| works in one terminal only | executable, edition, architecture, OS/WSL route | Invoke the intended host explicitly or correct that terminal's profile/`PATH` |
| glyph is a box or garbled | UTF-8 output and terminal font | Enable UTF-8/use a glyph-capable font, or set `LEAF_GLYPHS=ascii` |
| pack selected but no prompt glyph | subsystem PID/lease evidence | Start or identify the owned subsystem; selection alone is intentionally inactive |

## Multi-machine qualification

Do not turn “tested by more than ten people” into an unverifiable release claim.
Record at least eleven independent host results before making that claim. The
minimum useful matrix is:

1. Windows 10, Windows PowerShell 5.1;
2. Windows 11, Windows PowerShell 5.1;
3. Windows, PowerShell 7 MSI installation;
4. Windows, PowerShell 7 Store alias;
5. Windows, PowerShell 7 installed but absent from `PATH`;
6. a LeafOS root containing spaces or a synchronized-folder segment;
7. a deliberately missing or parser-damaged module in a disposable copy;
8. Git Bash/MSYS2 using Windows PowerShell interop;
9. WSL Ubuntu with native `pwsh`;
10. WSL Ubuntu using Windows `pwsh.exe` interop;
11. WSL Debian/AlmaLinux using the Windows PowerShell 5.1 fallback;
12. a managed or restricted execution-policy environment, when available.

For each run, store an anonymized host fingerprint, exact command, exit code,
doctor JSON, expected result, actual result, and repair effectiveness. Never
collect usernames, machine names, tokens, model contents, or unrelated paths.

Local automated coverage and local WSL checks are pre-release evidence; they are
not a substitute for this independent-host qualification.
