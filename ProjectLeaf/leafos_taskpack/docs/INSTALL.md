# LeafOS Installation Guide

Version: 0.5.0 | Updated: 2026-07-21

This guide retains installation and optional LAN distribution detail. The
current post-install project path is:

```powershell
.\bin\leafctl.ps1 doctor
.\bin\leafctl.ps1 provider-stack check
.\bin\leafctl.ps1 live C:\R\MyProject
```

Node initialization is optional. It is not required for a local resident run.
Model weights are managed separately through `models-install`; no install or
post-install command downloads weights without an explicit apply and `--yes`.

---

## Contents

1. [Requirements](#requirements)
2. [Method A — LAN pull (recommended for clusters)](#method-a--lan-pull)
3. [Method B — User-space application install](#method-b--user-space-application-install)
4. [Method C — Legacy taskpack demo installers](#method-c--legacy-taskpack-demo-installers)
5. [Method D — macOS](#method-d--macos)
6. [Post-install: initialise an optional node](#post-install-initialise-a-node)
7. [Verify the install](#verify-the-install)
8. [Uninstall](#uninstall)

---

## Requirements

| Component  | Minimum | Notes                          |
|------------|---------|--------------------------------|
| Bash       | 4.0     | macOS ships 3.x — use Homebrew |
| Python     | 3.8     | 3.12 recommended               |
| GCC / cc   | 9.0     | for C loader demo only         |
| PowerShell | 7.0     | Windows & cross-platform mode  |
| SSH client | any     | for node-to-node transport     |

Check all requirements at once:

```sh
leaf versions
```

---

## Method A — LAN pull

This is the fastest way to get LeafOS onto a second machine when one node is
already running.

### On the source node (already has LeafOS)

```sh
leaf serve
# or with options:
leaf serve --port 7771 --once
```

The terminal shows a live banner:

```
┌──────────────────────────────────────────────────────────┐
│  LeafOS v0.5.0  SERVE  ◉ ACTIVE  192.168.4.44            │
│  port  7771   pid  4812   requests  0                     │
├──────────────────────────────────────────────────────────┤
│  leafos-0.5.0.tar.gz   1.2 MB                            │
│    sha256: a3f8...                                       │
│  leafos-0.5.0.zip      1.3 MB                            │
│    sha256: 9c12...                                       │
├──────────────────────────────────────────────────────────┤
│  pull from another node:                                 │
│    leaf download 192.168.4.44                            │
└──────────────────────────────────────────────────────────┘
```

### On the target node

```sh
# auto-detect and download the .tar.gz
leaf download 192.168.4.44

# download to a specific folder
leaf download 192.168.4.44 --dest /tmp

# download specific file
leaf download 192.168.4.44 leafos-0.5.0.zip

# check what is available before downloading
leaf dist-info 192.168.4.44
```

SHA256 is always verified automatically after download.

### Unpack and install

```sh
cd /tmp
tar -xzf leafos-0.5.0.tar.gz
cd leafos-0.5.0
bash bin/install_demo.sh          # Linux / WSL
# or
bash bin/install_demo.sh ~/opt    # custom prefix
```

---

## Method B — User-space application install

The current application installer follows a plan/apply/verify contract. It is
safe to run from a source checkout and installs only the LeafOS launchers and
authoritative application tree into a detached user prefix. It does not
download or resolve models, start a provider, modify runtime routes, edit a
shell profile, or alter `PATH`.

```powershell
cd C:\R\LeafOS0.2.1

# Review the exact destination and safety boundary; makes no changes.
pwsh -NoProfile -File .\PowerShell-Version\install-leafos.ps1 -Action plan

# Copy the application and write a SHA-256 install manifest.
pwsh -NoProfile -File .\PowerShell-Version\install-leafos.ps1 -Action apply

# Verify every installed application file against the manifest.
pwsh -NoProfile -File .\PowerShell-Version\install-leafos.ps1 -Action verify
```

The default prefix is `%LOCALAPPDATA%\LeafOS`. Use `-Prefix C:\tools\LeafOS`
to select another user-writable location. `apply` refuses to replace an
existing application tree unless `-Force` is explicit. The installed launcher
is `<prefix>\bin\leafos.ps1`; invoke it directly or add that directory to
`PATH` manually if desired.

Model acquisition remains a separate operation under `models-install` and
requires its own explicit resolve/apply confirmation. Provider configuration
and Medium-MoE qualification remain separate, evidence-gated operations.

## Method C — Legacy taskpack demo installers

The following taskpack scripts are retained for demo/distribution scenarios.
They copy the taskpack directly and do not provide the current root-level
application install manifest contract.

```sh
git clone https://github.com/your-org/leafos_taskpack.git
cd leafos_taskpack
bash bin/install_demo.sh
```

The legacy installer copies the repo to `~/.local/share/leafos/` and symlinks
`leafctl` into `~/.local/bin/`.  Add `~/.local/bin` to `$PATH` if it is not
already there:

```sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

### Legacy Windows taskpack installer

```powershell
# From repo root in PowerShell:
pwsh -File bin\install_demo.ps1

# Custom prefix:
pwsh -File bin\install_demo.ps1 -Prefix C:\tools\leafos
```

The PowerShell installer:
- Copies files to `%LOCALAPPDATA%\leafos\share\leafos\`
- Installs `LeafOS.psm1` into your PowerShell module path
- Adds the bin dir to your `PATH` (User scope)

After install, reload your shell and run:

```powershell
Import-Module LeafOS
leaf status
```

---

## Method D — macOS

macOS ships Bash 3.x. Install Bash 5 first:

```sh
brew install bash python3
sudo bash -c 'echo /opt/homebrew/bin/bash >> /etc/shells'
chsh -s /opt/homebrew/bin/bash   # optional; makes it default
```

Then follow **Method B**:

```sh
git clone ...
cd leafos_taskpack
bash bin/install_mac.sh
```

---

## Post-install: initialise a node

Every machine that will receive or run tasks needs a Leaf workspace:

```sh
leaf node init
# or with explicit identity:
leaf node init --node-id "gpu-box-1" --role worker
```

The workspace is created at `~/.leaf/` (override with `LEAF_HOME`).

---

## Verify the install

```sh
leaf status          # system check
leaf versions        # component versions
leaf doctor          # deeper diagnostics
leaf node status     # node workspace check
leaf dashboard       # live status window
```

Expected output:

```
✓ leafctl found
✓ bash 5.2 ≥ 4.0
✓ python 3.12 ≥ 3.8
✓ node initialised: MiniPC  role: worker  state: ready
```

---

## Uninstall

**Linux / macOS**

```sh
rm -rf ~/.local/share/leafos ~/.leaf
rm -f ~/.local/bin/leafctl
```

**Windows**

```powershell
Remove-Item -Recurse "$env:LOCALAPPDATA\leafos"
Remove-Item -Recurse "$env:USERPROFILE\.leaf"
# Remove from PATH manually in System > Environment Variables
```
