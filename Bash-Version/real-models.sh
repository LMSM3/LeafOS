#!/usr/bin/env bash
# LeafOS real-model-first workflow for Bash.

# shellcheck source=../ProjectLeaf/leafos_taskpack/core/brand/palette.sh
_BRAND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ProjectLeaf/leafos_taskpack/core/brand"
if [[ -f "$_BRAND_DIR/palette.sh" ]]; then source "$_BRAND_DIR/palette.sh"; fi
unset _BRAND_DIR



set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$HERE/.." && pwd)"
INSTALLER="$ROOT_DIR/ProjectLeaf/leaf_model_installer"
CATALOG="$INSTALLER/leaf_models/model_catalog.json"
PROFILE="runtime-default"
MODEL_DIR="${LEAF_MODEL_DIR:-$HOME/.leaf/models}"
OUT_DIR="$HERE/reports/real-models"
RESOLVE=0
APPLY=0
YES=0
STATUS_ONLY=0
NO_ANIMATION="${NO_ANIMATION:-0}"
ALLOW_FALLBACK=0
MAX_WORKERS=8
CONTINUE_ON_ERROR=0
INCLUDE_EXPERIMENTAL=0
CONFIRM_HEAVY=""
HASH_VERIFY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --resolve) RESOLVE=1; shift ;;
    --apply) APPLY=1; shift ;;
    --yes) YES=1; shift ;;
    --status-only) STATUS_ONLY=1; shift ;;
    --no-animation) NO_ANIMATION=1; shift ;;
    --allow-fallback) ALLOW_FALLBACK=1; shift ;;
    --max-workers) MAX_WORKERS="$2"; shift 2 ;;
    --continue-on-error) CONTINUE_ON_ERROR=1; shift ;;
    --include-experimental) INCLUDE_EXPERIMENTAL=1; shift ;;
    --confirm-heavy) CONFIRM_HEAVY="$2"; shift 2 ;;
    --hash-verify) HASH_VERIFY=1; shift ;;
    --model-dir) MODEL_DIR="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    *) printf 'unknown flag: %s\n' "$1" >&2; exit 2 ;;
  esac
done

if [[ -z "${LEAF_MODEL_DIR:-}" && "$MODEL_DIR" == "$HOME/.leaf/models" && -d "$INSTALLER/models" ]]; then
  if find "$INSTALLER/models" -type f -name '*.gguf' -print -quit 2>/dev/null | grep -q .; then
    MODEL_DIR="$INSTALLER/models"
    MODEL_DIR_REASON="detected existing local GGUF cache"
  else
    MODEL_DIR_REASON="catalog default"
  fi
elif [[ -n "${LEAF_MODEL_DIR:-}" ]]; then
  MODEL_DIR_REASON="LEAF_MODEL_DIR environment variable"
else
  MODEL_DIR_REASON="explicit/default model directory"
fi

SAFE_PROFILE="$(printf '%s' "$PROFILE" | tr -c 'A-Za-z0-9._-' '_')"
PLAN="$OUT_DIR/leaf-$SAFE_PROFILE-plan.json"
RESOLVED="$OUT_DIR/leaf-$SAFE_PROFILE-plan.resolved.json"
REPORT="$OUT_DIR/real-model-status-$SAFE_PROFILE.json"
VERIFY_REPORT="$OUT_DIR/leaf-$SAFE_PROFILE-verify.json"
mkdir -p "$OUT_DIR"

animate() {
  local label="$1"
  leaf_transition "$label" model 8 "$(leaf_motion_delay 0.08)"
}

pick_python() {
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  if command -v python >/dev/null 2>&1; then
    command -v python
    return
  fi
  if [[ -x "$INSTALLER/.venv/bin/python" ]]; then
    printf '%s\n' "$INSTALLER/.venv/bin/python"
    return
  fi
  if [[ -x "$INSTALLER/.venv/bin/python3" ]]; then
    printf '%s\n' "$INSTALLER/.venv/bin/python3"
    return
  fi
  if [[ -x "$INSTALLER/.venv/Scripts/python.exe" ]]; then
    printf '%s\n' "$INSTALLER/.venv/Scripts/python.exe"
    return
  fi
  printf 'python/python3 not found; model helpers require Python.\n' >&2
  exit 2
}

leaf_models() {
  if [[ -f "$INSTALLER/leaf_models/install_cli.py" ]]; then
    PYTHONPATH="$INSTALLER${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -B -m leaf_models.install_cli "$@"
    return
  fi
  printf 'leaf model installer not found: %s\n' "$INSTALLER" >&2
  exit 2
}

write_status() {
  local status_args=(
    local-status
    --profile "$PROFILE"
    --dest "$MODEL_DIR"
    --model-dir-reason "$MODEL_DIR_REASON"
    --report "$REPORT"
    --plan "$PLAN"
    --resolved-plan "$RESOLVED"
    --verification-report "$VERIFY_REPORT"
  )
  if [[ "$ALLOW_FALLBACK" == "1" ]]; then status_args+=(--allow-fallback); fi
  leaf_models "${status_args[@]}"
}

PYTHON_BIN="$(pick_python)"

printf '\n%s╔══════════════════════════════════════════════════════════════════════╗%s\n' "$C_SKY" "$C_RESET"
printf '%s║                 LeafOS Real Models First                           ║%s\n' "$C_LEAF" "$C_RESET"
printf '%s╚══════════════════════════════════════════════════════════════════════╝%s\n\n' "$C_SKY" "$C_RESET"
printf 'profile:   %s\n' "$PROFILE"
printf 'model dir: %s\n' "$MODEL_DIR"
printf 'reason:    %s\n' "$MODEL_DIR_REASON"
printf 'reports:   %s\n\n' "$OUT_DIR"

animate "checking catalog-backed model files"
status_code=0
write_status || status_code=$?
if [[ "$status_code" -eq 2 ]]; then exit 2; fi

complete=false
if [[ "$status_code" -eq 0 ]]; then complete=true; fi

if [[ "$STATUS_ONLY" == "1" ]]; then
  [[ "$complete" == "true" ]] || exit 1
  exit 0
fi

animate "writing offline $PROFILE plan"
plan_args=(plan --profile "$PROFILE" --dest "$MODEL_DIR" --out "$PLAN")
if [[ "$ALLOW_FALLBACK" == "1" ]]; then plan_args+=(--allow-fallback); fi
leaf_models "${plan_args[@]}"

if [[ "$APPLY" == "1" && "$RESOLVE" != "1" ]]; then
  printf 'apply requires --resolve first\n' >&2
  exit 2
fi

if [[ "$RESOLVE" == "1" ]]; then
  animate "resolving exact files; metadata only"
  leaf_models resolve "$PLAN" --out "$RESOLVED"
fi

if [[ "$APPLY" == "1" ]]; then
  [[ "$YES" == "1" ]] || { printf 'apply downloads weights; add --yes\n' >&2; exit 2; }
  animate "downloading/resuming real model files"
  apply_args=(apply "$RESOLVED" --yes --max-workers "$MAX_WORKERS")
  if [[ "$CONTINUE_ON_ERROR" == "1" ]]; then apply_args+=(--continue-on-error); fi
  if [[ "$INCLUDE_EXPERIMENTAL" == "1" ]]; then apply_args+=(--include-experimental); fi
  if [[ -n "$CONFIRM_HEAVY" ]]; then apply_args+=(--confirm-heavy "$CONFIRM_HEAVY"); fi
  leaf_models "${apply_args[@]}"

  animate "verifying real model files"
  verify_args=(verify "$RESOLVED" --out "$VERIFY_REPORT")
  if [[ "$HASH_VERIFY" == "1" ]]; then verify_args+=(--hash); fi
  leaf_models "${verify_args[@]}"
  printf 'verification report: %s\n' "$VERIFY_REPORT"

  animate "refreshing local model status"
  status_code=0
  write_status || status_code=$?
  if [[ "$status_code" -eq 2 ]]; then exit 2; fi
  complete=false
  if [[ "$status_code" -eq 0 ]]; then complete=true; fi
fi

if [[ "$complete" == "true" ]]; then
  printf '\n%sReal model artifacts for %s are present.%s\n' "$C_LEAF" "$PROFILE" "$C_RESET"
else
  printf '\n%sReal model artifacts for %s are not complete yet.%s\n' "$C_BUTTER" "$PROFILE" "$C_RESET"
  printf 'Next safe step:\n  bash real-models.sh --profile %s --resolve\n' "$PROFILE"
  printf 'Download boundary after review:\n  bash real-models.sh --profile %s --resolve --apply --yes\n' "$PROFILE"
fi
