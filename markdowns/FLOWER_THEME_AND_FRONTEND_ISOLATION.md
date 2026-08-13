# FlowerOS Green + Pastel Theme & Frontend Isolation Reflection

## 1. Why this document exists

This workspace contains two cooperating systems:

- **FlowerOS** — the operating-layer surface (in `C:\R\FlowerOS`).
- **LeafOS** — the operator-facing control plane (in the active LeafOS repository root).

LeafOS is meant to run *alongside* and eventually *under* FlowerOS. A shared visual language helps a user feel that the two layers are one garden rather than two gardens with different fences.

The user asked for "several shades of green, and pastels" and then said "apply this theme across the entire codebase." This document records the exact values, the symbols, where the changes landed, why they landed there, and how to keep the CLI richness from leaking into business logic.

---

## 2. The canonical palette

There is exactly **one** true-color palette. All language layers derive from it.

### 2.1 Colors

| Name      | Hex         | RGB                | Role                         |
|-----------|-------------|--------------------|------------------------------|
| `mint`    | `#B7F0C7`   | 183, 240, 199      | primary success / status ok  |
| `leaf`    | `#77DD77`   | 119, 221, 119      | secondary success / action   |
| `fern`    | `#50B450`   |  80, 180,  80      | structural green             |
| `forest`  | `#228B22`   |  34, 139,  34      | strong structural / roots    |
| `bloom`   | `#FFB7C5`   | 255, 183, 197      | pink accent / flower glyph   |
| `lavender`| `#CCB2FF`   | 204, 178, 255      | soft highlight               |
| `sky`     | `#B2DFFF`   | 178, 223, 255      | info / water / cyan role     |
| `butter`  | `#FFFAB5`   | 255, 250, 181      | warning / caution            |
| `peach`   | `#FFD2B7`   | 255, 210, 183      | warm warning                 |
| `error`   | `#FF9AA2`   | 255, 154, 162      | red, errors                  |

### 2.2 ANSI sequences

Every color is emitted as a true-color foreground escape:

```
\033[38;2;<R>;<G>;<B>m
```

Reset and style modifiers:

- reset: `\033[0m`
- bold:  `\033[1m`
- dim:   `\033[2m`

### 2.3 Environment controls

All CLI surfaces honor the same contract:

| Variable        | Value(s)        | Effect                                    |
|-----------------|-----------------|-------------------------------------------|
| `NO_COLOR`      | `1`             | Disable all color output                  |
| `LEAF_COLOR`    | `1` / `yes` / `true` | Force color even on non-tty pipes  |
| `FORCE_COLOR`   | `1` / `yes` / `true` | Alias for `LEAF_COLOR`             |
| `NO_EMOJI`      | `1`             | Prefer ASCII fallbacks for glyphs         |

---

## 3. Where the palette is defined

### 3.1 Python — `ProjectLeaf/leafos_taskpack/core/brand/flower_palette.py`

This is a dependency-free module. Any Python CLI surface can `from flower_palette import color, paint` without dragging in the rest of LeafOS.

Key exports:

- `PALETTE` — dict of name → escape string
- `no_color()` — respects `NO_COLOR`, `LEAF_COLOR`, `FORCE_COLOR`, and `isatty`
- `color(name)` — returns the escape or `''`
- `paint(text, *names)` — wraps text in named colors and resets

### 3.2 Bash — two files

- `ProjectLeaf/leafos_taskpack/core/brand/palette.sh` — standalone, idempotent, sourced by any LeafOS bash frontend.
- `FlowerOS/lib/colors.sh` — FlowerOS native palette, already sourced by FlowerOS scripts.
- `ProjectLeaf/leafos_taskpack/core/brand/brand.sh` — also initializes the same variables with the same names for legacy callers.

Bash variables exported:

```bash
C_RESET C_BOLD C_DIM
C_MINT C_LEAF C_FERN C_FOREST
C_BLOOM C_LAVENDER C_SKY C_BUTTER C_PEACH C_ERROR
C_GREEN C_CYAN C_YELLOW C_RED C_MAGENTA C_BLUE
C_GREEN_B C_CYAN_B C_YELLOW_B C_RED_B
```

The legacy variables (`C_GREEN`, `C_CYAN`, etc.) are aliases into the new palette so old callers continue to work.

### 3.3 PowerShell — `ProjectLeaf/leafos_taskpack/core/powershell/LeafOS.psm1`

The module exposes:

- `$script:LeafColor` hashtable with all named true-color escapes.
- `_leaf_should_use_color` private helper respecting `NO_COLOR`/`LEAF_COLOR`/`FORCE_COLOR`.
- `Write-LeafMsg` now uses the palette.

---

## 4. Symbol / glyph vocabulary

| Glyph  | Unicode | ASCII fallback | Meaning                |
|--------|---------|----------------|------------------------|
| `✓`    | U+2713  | `[ok]`         | success / passed       |
| `✗`    | U+00D7  | `[x]`          | failure / error        |
| `⚠`    | U+26A0  | `[!]`          | warning                |
| `◌`    | U+25CC  | `[..]`         | pending / unknown      |
| `🌱`   | U+1F331 | `LeafOS`       | brand / leaf           |
| `✿`    | U+273F  | `*`            | flower / accent        |
| `❦`    | U+2766  | `WO`           | work order             |
| `⌂`    | U+2302  | `home`         | home / latest run      |

The canonical registry is `ProjectLeaf/leafos_taskpack/config/glyphs.conf`; Python `home.py` mirrors the subset it needs.

---

## 5. Files that changed

### LeafOS

- `ProjectLeaf/leafos_taskpack/core/ui/menu.py` — **new** shared palette-aware menu renderer with categorized choices, glyphs, shortcuts, and a placeholder "Agentic Stack" inlet.
- `ProjectLeaf/leafos_taskpack/core/ui/home.py` — card renderer now imports `flower_palette` and uses it for every section heading/status; Next Actions are grouped by category and glyph.
- `ProjectLeaf/leafos_taskpack/core/ui/home_state.py` — Next Actions now carry `category` and `glyph`; FlowerOS bridge actions and an interactive-menu action are added.
- `ProjectLeaf/leafos_taskpack/core/ui/tui/router.py` — bottom-bar prompt strings use the palette for soft pastel hints.
- `ProjectLeaf/leafos_taskpack/core/brand/flower_palette.py` — new canonical Python palette.
- `ProjectLeaf/leafos_taskpack/core/brand/palette.sh` — new standalone bash palette.
- `ProjectLeaf/leafos_taskpack/core/brand/brand.sh` — extended to true-color palette + `LEAF_COLOR`/`FORCE_COLOR`.
- `ProjectLeaf/leafos_taskpack/core/glyphs/glyphs.sh` — severity colors now use `C_LEAF`, `C_BUTTER`, `C_ERROR`, `C_SKY`.
- `ProjectLeaf/leafos_taskpack/core/powershell/LeafOS.psm1` — PowerShell palette + helper.
- `ProjectLeaf/leaf_model_installer/leaf_models/install_cli.py` — `_color()` maps legacy names to the true-color palette.
- `ProjectLeaf/install/windows/download-pack-aria2.py` — 256-color output remapped to FlowerOS true-color.
- `ProjectLeaf/install/windows/download-pack-hftransfer.py` — same remapping.
- `Bash-Version/*.sh` — all bash installer scripts source `palette.sh` and use `${C_*}` variables.
- `PowerShell-Version/leaf.ps1` — UTF-8 console encodings already present.

### FlowerOS

- `FlowerOS/lib/colors.sh` — expanded to several shades of green + pastels; `ok()`/`warn()`/`info()` use pastel tones.
- `FlowerOS/lib/banners.sh` — default `_FOS_*` colors switched to true-color palette values.
- `FlowerOS/lib/state.sh` — new `flower_state_theme()` command and pastel/green `flower_state_show()` output.
- `FlowerOS/bin/flower-state` — added `theme` subcommand.

---

## 6. Optimization: isolate CLI richness to a single directory

The long-term goal is to make the rest of the codebase **presentation-agnostic**. Only one directory should contain color, glyphs, banners, and spinner logic.

### 6.1 Proposed single directory

```
ProjectLeaf/leafos_taskpack/core/brand/
├── flower_palette.py      # Python palette
├── palette.sh             # Bash palette (and/or make brand.sh source this)
├── LeafOS.psm1            # PowerShell palette module (moved from core/powershell)
├── glyphs.conf            # already exists; keep as canonical glyph registry
├── glyphs.sh              # bash glyph renderer (already here)
├── brand.sh               # legacy banner helpers (already here)
├── spinners.sh            # NEW: shared animation frames for bash
└── README.md              # NEW: how to use the brand layer
```

### 6.2 Rules for the rest of the codebase

1. **No raw ANSI codes outside `core/brand/`**. Any `\033[` string appearing in a new script is a bug.
2. **No `Write-Host -ForegroundColor` outside brand module**. Frontends call `Write-LeafMsg` or import the module.
3. **No emoji/symbol literals outside `config/glyphs.conf` and `home.py`**. Treat the conf file as the single source of truth.
4. **Business logic returns data; presentation formats data.** `home_state.py` returns JSON; `home.py` renders it.
5. **Environment controls are centralized.** `NO_COLOR`/`LEAF_COLOR`/`FORCE_COLOR` should be read only inside the brand layer, not by individual commands.

### 6.3 Menu conventions

New menus should follow the pattern used by `core/ui/menu.py`:

- **Categories** are pastel section headers (`blossom` + `semibold`).
- **Numbers** are rendered in `blossom`.
- **Glyphs** use the shared vocabulary; unknown glyphs fall back to the flower.
- **Shortcuts** are one-letter hints in `lavender` brackets.
- **Disabled items** are dimmed.
- **Quit** is always `0` or `q` and uses the peach error color.

Example menu actions from `leaf menu`:

```python
{"label": "Open local chat", "command": "& '...\\leaf.ps1' chat", "category": "Chat", "glyph": "chat", "shortcut": "c"},
{"label": "Open local stack", "command": "& '...\\leaf.ps1' stack --agent-inlet", "category": "Agentic Stack", "glyph": "stack", "shortcut": "s"},
```

### 6.4 Migration path

The following surfaces still carry legacy hardcoded colors and should migrate next:

- `ProjectLeaf/leaf_model_installer/shell_helpers/*.ps1`
- `ProjectLeaf/leaf_model_installer/install.ps1`
- `PowerShell-Version/chat-local.ps1`
- `PowerShell-Version/install-leafos.ps1`
- `FlowerOS/install-themes.ps1`

For each:

1. Import the appropriate brand module.
2. Replace raw codes / `Write-Host -ForegroundColor` with named color calls.
3. Preserve ASCII fallbacks with `NO_EMOJI=1`.
4. Add a smoke test to `t/brand-smoke.t` (bash/py/pwsh).

### 6.5 Testing checklist

- [ ] `NO_COLOR=1 ./script` produces no escape sequences.
- [ ] `LEAF_COLOR=1 ./script | cat` still produces escape sequences.
- [ ] `NO_EMOJI=1` prints ASCII fallbacks.
- [ ] The same script works in PowerShell 5.1 and PowerShell 7+.
- [ ] Python surfaces run with `--json` and emit no ANSI codes.

---

## 7. Reflections and trade-offs

### Why true-color instead of 256-color?

The old code used both xterm-256 codes (`\033[38;5;210m`) and basic 16-color codes (`\033[32m`). True-color (`\033[38;2;R;G;Bm`) is the only way to guarantee the exact pastel shades on modern terminals, Windows Terminal, and most Linux consoles. It does not degrade on older terminals — they simply show the closest color they can.

### Why not just one shared cross-language file?

A JSON or TOML palette file shared by Python, bash, and PowerShell would be ideal. The current step keeps each language’s palette in its own idiomatic file. The next refactoring should generate `palette.sh`, `flower_palette.py`, and the PowerShell hashtable from a single `palette.json` at build time.

### Why `LEAF_COLOR` and `FORCE_COLOR`?

- `NO_COLOR` is the community standard for disabling color.
- `FORCE_COLOR` is the community standard for forcing color.
- `LEAF_COLOR` is project-specific and easy to remember for LeafOS/FlowerOS operators.

Supporting both costs nothing and matches user expectations.

### Why keep ASCII fallbacks?

Glyphs like `✓`, `🌱`, and `✿` fail on some Windows shells, old fonts, and narrow terminals. The fallback path (`NO_EMOJI=1`) keeps the interface readable everywhere.

---

## 8. Quick reference for new surfaces

### Python

```python
from flower_palette import color, paint
print(paint('ready', 'leaf'))
print(paint('[!] slow', 'butter'))
```

### Bash

```bash
source "$(cd "$(dirname "$0")" && pwd)/../ProjectLeaf/leafos_taskpack/core/brand/palette.sh"
printf '%sOK%s\n' "${C_LEAF}" "${C_RESET}"
printf '%swarning%s\n' "${C_BUTTER}" "${C_RESET}"
```

### PowerShell

```powershell
Import-Module "$env:LEAF_ROOT\ProjectLeaf\leafos_taskpack\core\powershell\LeafOS.psm1"
Write-Host "$($script:LeafColor.Mint)ready$($script:LeafColor.Reset)"
```

---

## 9. Final note

The garden metaphor is not decorative. The four greens represent growth stages; the pastels represent the conditions that let growth happen — light, water, blossom, and warning sun. Keeping the palette consistent across FlowerOS and LeafOS makes the operator feel they are tending one system, not two.
