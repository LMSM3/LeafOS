#!/usr/bin/env bash
set -euo pipefail

# Compatibility wrapper. It plans only unless --resolve/--apply are explicit.
slot=1
quant=""
dest="${LEAF_MODEL_DIR:-$HOME/.leaf/models}"
plan="./leaf-model-plan.json"
resolve=0
apply=0
yes=0
allow_fallback=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --slot) slot="${2:?missing slot}"; shift 2 ;;
    --quant) quant="${2:?missing quant}"; shift 2 ;;
    --dest) dest="${2:?missing destination}"; shift 2 ;;
    --plan) plan="${2:?missing plan path}"; shift 2 ;;
    --allow-fallback) allow_fallback=1; shift ;;
    --resolve) resolve=1; shift ;;
    --apply) apply=1; shift ;;
    --yes) yes=1; shift ;;
    -h|--help)
      printf 'Usage: download-model.sh [--slot 1-5] [--quant Q4_K_M] [--dest DIR] [--resolve] [--apply --yes]\n'
      exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
launcher="$root/leaf-models"
[[ -x "$launcher" ]] || {
  printf 'Installer launcher missing. Run install.sh first.\n' >&2
  exit 2
}

args=(plan --slot "$slot" --dest "$dest" --out "$plan")
[[ -n "$quant" ]] && args+=(--quant "$slot=$quant")
[[ "$allow_fallback" -eq 1 ]] && args+=(--allow-fallback)
"$launcher" "${args[@]}"

resolved="${plan%.json}.resolved.json"
if [[ "$resolve" -eq 1 || "$apply" -eq 1 ]]; then
  "$launcher" resolve "$plan" --out "$resolved"
fi
if [[ "$apply" -eq 1 ]]; then
  [[ "$yes" -eq 1 ]] || { printf '%s\n' '--apply requires --yes.' >&2; exit 2; }
  exec "$launcher" apply "$resolved" --yes
fi
printf 'Plan prepared. No model download was started.\n'
exit 0

# Legacy implementation below is unreachable and retained for migration history.

model="gemma4-coder"
quant="Q4_K_M"
dest="./models"
verify_only=0
min_bytes=1048576

fail() {
  printf 'FAILED: %s\n' "$1" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model) model="${2:-}"; shift 2 ;;
    --quant) quant="${2:-}"; shift 2 ;;
    --dest) dest="${2:-}"; shift 2 ;;
    --verify-only) verify_only=1; shift ;;
    --min-bytes) min_bytes="${2:-}"; shift 2 ;;
    -h|--help)
      cat <<'HELP'
Usage: ./shell_helpers/download-model.sh [--model gemma4-coder|qwen-opus-reasoning] [--quant Q4_K_M] [--dest ./models] [--verify-only]
Shell-only fallback that calls huggingface-cli directly, then verifies the local GGUF files.
HELP
      exit 0 ;;
    *) fail "Unknown argument: $1" ;;
  esac
done

case "$model" in
  gemma4-coder)
    repo="yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF"
    local_dir="Gemma4-Coder"
    case "$quant" in
      Q2_K) pattern='*Q2_K*.gguf' ;;
      Q3_K_M) pattern='*Q3_K_M*.gguf' ;;
      Q4_K_M) pattern='*Q4_K_M*.gguf' ;;
      Q6_K) pattern='*Q6_K*.gguf' ;;
      Q8_0) pattern='*Q8_0*.gguf' ;;
      *) fail "Unknown quant: $quant" ;;
    esac ;;
  qwen-opus-reasoning)
    repo="tvall43/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap-gguf"
    local_dir="Qwen3.5-Claude-Reasoning"
    pattern='*.gguf' ;;
  *) fail "Unknown model: $model" ;;
esac

mkdir -p "$dest"
target="$(cd "$dest" && pwd)/$local_dir"
mkdir -p "$target"

printf 'Model:   %s\n' "$model"
printf 'Repo:    %s\n' "$repo"
printf 'Pattern: %s\n' "$pattern"
printf 'Target:  %s\n' "$target"

if [[ "$verify_only" -eq 0 ]]; then
  command -v huggingface-cli >/dev/null 2>&1 || fail "huggingface-cli not found. Run the main installer first or install huggingface_hub."
  huggingface-cli download "$repo" --include "$pattern" --local-dir "$target"
fi

mapfile -t files < <(find "$target" -type f -name "$pattern" -print | sort)
if [[ "${#files[@]}" -eq 0 ]]; then
  fail "No files matching $pattern found under $target"
fi

bad=0
for file in "${files[@]}"; do
  bytes=$(wc -c < "$file" | tr -d ' ')
  if [[ "$bytes" -lt "$min_bytes" ]]; then
    printf 'BAD tiny file: %s (%s bytes)\n' "$file" "$bytes" >&2
    bad=1
  fi
done
[[ "$bad" -eq 0 ]] || fail "Verification failed"

manifest="$target/leaf_shell_manifest.txt"
{
  printf 'created_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'repo=%s\n' "$repo"
  printf 'pattern=%s\n' "$pattern"
  printf 'target=%s\n' "$target"
  printf 'files=%s\n' "${#files[@]}"
} > "$manifest"

for file in "${files[@]}"; do
  bytes=$(wc -c < "$file" | tr -d ' ')
  gb=$(awk -v b="$bytes" 'BEGIN { printf "%.2f", b / 1024 / 1024 / 1024 }')
  printf 'OK  %8s GB  %s\n' "$gb" "$file"
done
printf 'VERIFIED: files exist at %s\n' "$target"
printf 'Manifest: %s\n' "$manifest"
