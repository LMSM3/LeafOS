#!/usr/bin/env bash
# LeafOS Bash installation/readiness check.

# shellcheck source=../ProjectLeaf/leafos_taskpack/core/brand/palette.sh
_BRAND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ProjectLeaf/leafos_taskpack/core/brand"
if [[ -f "$_BRAND_DIR/palette.sh" ]]; then source "$_BRAND_DIR/palette.sh"; fi
unset _BRAND_DIR



set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEAF="$HERE/leaf.sh"
MODELS="$HERE/real-models.sh"
ONESHOT="$HERE/oneshot.sh"
NO_ANIMATION="${NO_ANIMATION:-0}"
SKIP_DOCTOR=0
SKIP_MODEL_PLAN=0
SKIP_ONESHOT_PREVIEW=0
REPORT_DIR="$HERE/reports/install-$(date '+%Y%m%d-%H%M%S')"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-animation) NO_ANIMATION=1; shift ;;
    --skip-doctor) SKIP_DOCTOR=1; shift ;;
    --skip-model-plan) SKIP_MODEL_PLAN=1; shift ;;
    --skip-oneshot-preview) SKIP_ONESHOT_PREVIEW=1; shift ;;
    --report-dir) REPORT_DIR="$2"; shift 2 ;;
    *) printf 'unknown flag: %s\n' "$1" >&2; exit 2 ;;
  esac
done

mkdir -p "$REPORT_DIR"
LOG="$REPORT_DIR/install.log"
MANIFEST="$REPORT_DIR/install_manifest.json"

log_line() {
  printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >> "$LOG"
}

animate() {
  local label="$1"
  local style="${2:-leaf}"
  leaf_transition "$label" "$style" 12 "$(leaf_motion_delay 0.06)"
}

run_step() {
  local name="$1"
  local style="$2"
  local optional="${3:-0}"
  shift 3
  printf '\n==> %s\n' "$name"
  log_line "START $name"
  animate "$name" "$style"
  if "$@" 2>&1 | tee -a "$LOG"; then
    printf '%sOK: %s%s\n' "$C_LEAF" "$name" "$C_RESET"
    log_line "OK $name"
  else
    local code=$?
    printf '%sFAILED: %s%s\n' "$C_ERROR" "$name" "$C_RESET"
    log_line "FAILED $name code=$code"
    [[ "$optional" == "1" ]] || exit "$code"
  fi
}

printf '\n%s╔══════════════════════════════════════════════════════════════════════╗%s\n' "$C_SKY" "$C_RESET"
printf '%s║                       LeafOS Bash Installer                         ║%s\n' "$C_LEAF" "$C_RESET"
printf '%s║          real models first • offline plan • safe defaults           ║%s\n' "$C_SKY" "$C_RESET"
printf '%s╚══════════════════════════════════════════════════════════════════════╝%s\n\n' "$C_SKY" "$C_RESET"
printf 'root:    %s\n' "$ROOT_DIR"
printf 'command: %s\n' "$LEAF"
printf 'reports: %s\n\n' "$REPORT_DIR"
printf '%sSafety: checks local model files and writes plans, but does not resolve or download weights.%s\n' "$C_BUTTER" "$C_RESET"

run_step "Bash version check" orbit 0 bash -c '[[ "${BASH_VERSINFO[0]:-0}" -ge 4 ]]'

run_step "Python availability" bloom 1 bash -c 'command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1'

if [[ "$SKIP_DOCTOR" != "1" ]]; then
  run_step "LeafOS doctor" braille 0 bash "$LEAF" doctor
  run_step "Runtime validation" leaf 0 bash "$LEAF" runtime validate
  run_step "Runtime selection" leaf 0 bash "$LEAF" runtime select
fi

if [[ "$SKIP_MODEL_PLAN" != "1" ]]; then
  model_out="$REPORT_DIR/models"
  run_step "Real runtime model check and offline plan" comet 0 bash "$MODELS" --out-dir "$model_out" --no-animation
fi

if [[ "$SKIP_ONESHOT_PREVIEW" != "1" ]]; then
  preview_target="$REPORT_DIR/oneshot-preview"
  run_step "One-shot preview" bloom 1 bash "$ONESHOT" --oneshot .. "$preview_target" --dry-run
fi

cat > "$MANIFEST" <<EOF
{
  "schema_version": 1,
  "surface": "Bash-Version",
  "root": "$ROOT_DIR",
  "report_dir": "$REPORT_DIR",
  "safety": "offline model check; no resolve/apply/download"
}
EOF

printf '\n%sLeafOS Bash install automation complete.%s\n' "$C_LEAF" "$C_RESET"
printf 'manifest: %s\n' "$MANIFEST"
printf 'log:      %s\n\n' "$LOG"
printf 'Next commands:\n'
printf '  bash "%s/leafos.sh" q       # concise command card\n' "$ROOT_DIR"
printf '  bash "%s/leafos.sh"         # FlowerOS Home\n' "$ROOT_DIR"
printf '  bash "%s/leafos.sh" d       # doctor\n' "$ROOT_DIR"
printf '  bash install-real.sh                   # preview real install automation\n'
printf '  bash install-real.sh --yes             # resolve + download/resume + verify\n'
printf '  bash real-models.sh --resolve              # metadata only\n'
printf '  bash real-models.sh --resolve --apply --yes  # download boundary\n'
