# LeafOS Bash Version

This is the Bash-facing LeafOS surface.

Start here for Linux, macOS, WSL, MSYS2, or Git Bash.

## Install / check readiness

```bash
cd /path/to/LeafOS/Bash-Version
bash install.sh
```

## Usage

```bash
bash ../leafos.sh q
bash ../leafos.sh
bash ../leafos.sh d
bash ../leafos.sh r
bash ../leafos.sh ref
bash leaf.sh status
bash leaf.sh doctor
bash leaf.sh runtime select
bash leaf.sh web-state
bash oneshot.sh --oneshot .. ./LeafOS-OneShot
```

For the full command map and common workflows, read `../markdowns/USAGE.md`.
For the reusable-tool ownership and configuration boundaries, read
`../markdowns/ROOT_CONTRACT.md`.

## Model defaults

Real model check plus safe offline plan:

```bash
bash real-models.sh
```

Resolve metadata only:

```bash
bash real-models.sh --resolve
```

Download or resume only after review:

```bash
bash real-models.sh --resolve --apply --yes
```

Full real installation automation:

```bash
bash install-real.sh        # preview
bash install-real.sh --yes  # resolve + download/resume + verify
```

Download doctor:

```bash
bash leaf.sh download doctor
```

This hashes local model artifacts, waits one second, then prints each model
file's size and location. It performs no downloads.

Web/runtime state:

```bash
bash leaf.sh web-state --json
bash leaf.sh web-state --refresh-metadata --write
```

The default coding language is Python. The web-state command uses cached or
steady-state fallback metadata unless `--refresh-metadata` is explicitly set.

Runtime role rule: Fable/Gemma4-Coder is coding-only; Opus or another
main-model-pool model owns main and scheduler duties.

Apply is the model download boundary.

Compatibility alias:

```bash
bash models.sh
```
