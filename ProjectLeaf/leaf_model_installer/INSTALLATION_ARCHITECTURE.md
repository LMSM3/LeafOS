# LeafOS Model Installation Architecture

## Authority

`leaf_models/model_catalog.json` is the only model acquisition registry.
LeafOS post-install scripts, compatibility helpers, and CLI entrypoints delegate
to this package. They do not maintain independent repository lists.

## Phase boundary

```text
catalog
  -> plan       local only; selects slots, variants, destination
  -> resolve    metadata only; finds exact files and pins commit revisions
  -> apply      download boundary; explicit --yes required
  -> verify     checks every expected file against the resolved plan
```

An unresolved plan cannot be applied. This prevents a repository from changing
between review and transfer without the change being visible.

## Profiles

- `default`: slots 1 and 3, Fable coder plus Opus main/scheduler
- `runtime-default`: slots 1 and 3, matching the LeafOS empty-input runtime
- `extended`: slots 1, 3, and 4, adding deeper non-coder reasoning/planning
- `legacy-coder-pair`: slots 1 and 2, historical download profile only
- `experimental`: runtime slots, optional reasoning, legacy secondary coder, and guarded slot 5

Profiles are convenience selectors. The plan records the expanded slots and
variants, so execution does not depend on a profile changing later.

## Artifact policy

- Every GGUF selection uses an exact filename or quant-specific pattern.
- Blanket `*.gguf` selection is forbidden.
- Projectors, BF16 weights, MTP drafts, and training artifacts are excluded
  unless they are explicitly represented by a catalog variant.
- GPT-OSS is a snapshot with an allowlist of root model shards and runtime
  metadata. `original/` and `metal/` are excluded.

## State and recovery

Hugging Face's local cache retains partial files. Re-running `apply` with the
same resolved plan resumes those transfers.

LeafOS adds:

- a destination-wide exclusive install lock;
- JSONL events for each item transition;
- a final run manifest;
- exact post-transfer verification;
- fail-fast behavior by default;
- optional `--continue-on-error`.

The installer never deletes partial downloads automatically. Cleanup is a
separate operator decision because partial data may be valuable for resume.

## Failure rules

- Missing remote match: resolve fails.
- Unrequested fallback: resolve fails.
- Unknown aggregate size after resolve: apply fails.
- Insufficient disk space with 15% margin: apply fails.
- Existing install lock: apply fails.
- Missing or size-mismatched local file: verification fails.
- Any failed item makes the run manifest unsuccessful.

No downstream wrapper may replace those failures with a success message.

## Heavyweight guard

Any plan containing an experimental model requires both:

```text
--include-experimental
--confirm-heavy <model-key>
```

For slot 5 the confirmation key is `gpt-oss-120b`.

## Storage contract

Priority:

1. `LEAF_MODEL_DIR`
2. `~/.leaf/models`

Each model owns one stable subdirectory. Installer state is isolated beneath
`.leafos-installer` so model servers can ignore it.
