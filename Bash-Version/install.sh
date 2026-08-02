#!/usr/bin/env bash
# LeafOS Bash installation/readiness check.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEAF="$HERE/leaf.sh"
MODELS="$HERE/real-models.sh"
ONESHOT="$HERE/oneshot.sh"
NO_ANIMATION=0
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
  if [[ "$NO_ANIMATION" == "1" ]]; then
    printf '  -> %s\n' "$label"
    return
  fi
  local frames
  case "$style" in
    orbit) frames='◐ ◓ ◑ ◒' ;;
    bloom) frames='· ✿ ❀ ✽ ❁' ;;
    comet) frames='⠁ ⠂ ⠄ ⠂' ;;
    braille) frames='⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏' ;;
    *) frames='🍃 🌿 ☘ 🌱' ;;
  esac
  local frame i
  # shellcheck disable=SC2086
  set -- $frames
  for i in {0..11}; do
    eval "frame=\${$((i % $# + 1))}"
    printf '\r  \033[36m%s\033[0m %s   ' "$frame" "$label"
    sleep 0.06
  done
  printf '\r  \033[32m✓\033[0m %s   \n' "$label"
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
    printf '\033[32mOK: %s\033[0m\n' "$name"
    log_line "OK $name"
  else
    local code=$?
    printf '\033[31mFAILED: %s\033[0m\n' "$name"
    log_line "FAILED $name code=$code"
    [[ "$optional" == "1" ]] || exit "$code"
  fi
}

printf '\n\033[36m╔══════════════════════════════════════════════════════════════════════╗\033[0m\n'
printf '\033[32m║                       LeafOS Bash Installer                         ║\033[0m\n'
printf '\033[36m║          real models first • offline plan • safe defaults           ║\033[0m\n'
printf '\033[36m╚══════════════════════════════════════════════════════════════════════╝\033[0m\n\n'
printf 'root:    %s\n' "$ROOT_DIR"
printf 'command: %s\n' "$LEAF"
printf 'reports: %s\n\n' "$REPORT_DIR"
printf '\033[33mSafety: checks local model files and writes plans, but does not resolve or download weights.\033[0m\n'

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

printf '\n\033[32mLeafOS Bash install automation complete.\033[0m\n'
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
