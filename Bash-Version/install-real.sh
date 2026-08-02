#!/usr/bin/env bash
# LeafOS real installation automation for Bash.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$HERE/.." && pwd)"
LEAF="$HERE/leaf.sh"
REAL_MODELS="$HERE/real-models.sh"
RUNTIME_CONFIG="$ROOT_DIR/ProjectLeaf/leafos_taskpack/config/runtime.json"
PROFILE="runtime-default"
YES=0
NO_ANIMATION=0
SKIP_READINESS=0
ALLOW_FALLBACK=0
MAX_WORKERS=8
CONTINUE_ON_ERROR=0
INCLUDE_EXPERIMENTAL=0
CONFIRM_HEAVY=""
HASH_VERIFY=0
MODEL_DIR=""
REPORT_DIR="$HERE/reports/install-real-$(date '+%Y%m%d-%H%M%S')"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --yes) YES=1; shift ;;
    --no-animation) NO_ANIMATION=1; shift ;;
    --skip-readiness) SKIP_READINESS=1; shift ;;
    --allow-fallback) ALLOW_FALLBACK=1; shift ;;
    --max-workers) MAX_WORKERS="$2"; shift 2 ;;
    --continue-on-error) CONTINUE_ON_ERROR=1; shift ;;
    --include-experimental) INCLUDE_EXPERIMENTAL=1; shift ;;
    --confirm-heavy) CONFIRM_HEAVY="$2"; shift 2 ;;
    --hash-verify) HASH_VERIFY=1; shift ;;
    --model-dir) MODEL_DIR="$2"; shift 2 ;;
    --report-dir) REPORT_DIR="$2"; shift 2 ;;
    *) printf 'unknown flag: %s\n' "$1" >&2; exit 2 ;;
  esac
done

mkdir -p "$REPORT_DIR"
LOG="$REPORT_DIR/install-real.log"
MANIFEST="$REPORT_DIR/install-real-manifest.json"
MODEL_REPORT_DIR="$REPORT_DIR/models"
RUNTIME_ROLE_REPORT="$REPORT_DIR/runtime-role-policy.json"

log_line() {
  printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >> "$LOG"
}

animate() {
  local label="$1"
  if [[ "$NO_ANIMATION" == "1" ]]; then
    printf '  -> %s\n' "$label"
    return
  fi
  local frames=("🌱" "🌿" "GGUF" "⬇" "✓")
  local i
  for i in {0..9}; do
    printf '\r  \033[36m%s\033[0m %s   ' "${frames[$((i % ${#frames[@]}))]}" "$label"
    sleep 0.07
  done
  printf '\r  \033[32m✓\033[0m %s   \n' "$label"
}

run_step() {
  local name="$1"
  shift
  printf '\n==> %s\n' "$name"
  log_line "START $name"
  animate "$name"
  if "$@" 2>&1 | tee -a "$LOG"; then
    printf '\033[32mOK: %s\033[0m\n' "$name"
    log_line "OK $name"
  else
    local code=$?
    printf '\033[31mFAILED: %s\033[0m\n' "$name"
    log_line "FAILED $name code=$code"
    exit "$code"
  fi
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
  printf 'python/python3 not found; runtime role policy check requires Python.\n' >&2
  exit 2
}

write_role_policy_report() {
  local py
  py="$(pick_python)"
  "$py" - "$RUNTIME_CONFIG" "$RUNTIME_ROLE_REPORT" <<'PY'
import datetime as dt
import json
import sys

config_path, report_path = sys.argv[1:3]
with open(config_path, "r", encoding="utf-8") as handle:
    cfg = json.load(handle)
rt = cfg["leafos_runtime"]
coding = rt.get("role_policy", {}).get("coding_model_key", "gemma4-coder")
coder_pool = [item["key"] for item in rt["coder_models"]]
main_pool = [item["key"] for item in rt["main_models"]]
scheduler = rt["defaults"]["scheduler_model"]
if coder_pool != [coding]:
    raise SystemExit(f"Runtime role policy violation: coder model must be exactly {coding}")
if coding in main_pool:
    raise SystemExit(f"Runtime role policy violation: {coding} cannot be in main_models")
if scheduler in coder_pool:
    raise SystemExit("Runtime role policy violation: scheduler model cannot be a coder model")
if scheduler not in main_pool:
    raise SystemExit("Runtime role policy violation: scheduler default must be in main_models")
payload = {
    "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    "runtime_config": config_path,
    "complete": True,
    "coding_model": coding,
    "coding_scope": rt.get("role_policy", {}).get("coding_scope", "coding_only"),
    "scheduler_model": scheduler,
    "main_model": rt["defaults"]["main_model"],
    "main_and_scheduler_pool": main_pool,
    "coder_pool": coder_pool,
    "rule": "Fable/Gemma4-Coder is coding-only; Opus or another main model owns main and scheduler duties.",
}
with open(report_path, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2)
    handle.write("\n")
print(f"coding model    : {coding}")
print(f"main model      : {rt['defaults']['main_model']}")
print(f"scheduler model : {scheduler}")
print(f"policy report   : {report_path}")
PY
}

printf '\n\033[36m╔══════════════════════════════════════════════════════════════════════╗\033[0m\n'
printf '\033[32m║                  LeafOS Real Installation                          ║\033[0m\n'
printf '\033[36m║        resolve • download/resume • verify • report                  ║\033[0m\n'
printf '\033[36m╚══════════════════════════════════════════════════════════════════════╝\033[0m\n\n'
printf 'root:        %s\n' "$ROOT_DIR"
printf 'profile:     %s\n' "$PROFILE"
printf 'reports:     %s\n' "$REPORT_DIR"
printf 'max workers: %s\n\n' "$MAX_WORKERS"

if [[ "$YES" == "1" ]]; then
  printf '\033[33mREAL INSTALL ENABLED: this run may download large model weights.\033[0m\n'
else
  printf '\033[33mPreview mode: no network resolve and no download will be performed.\033[0m\n'
  printf '\033[33mTo run the real installation, re-run with --yes.\033[0m\n'
fi

run_step "Runtime role policy" write_role_policy_report

if [[ "$SKIP_READINESS" != "1" ]]; then
  run_step "LeafOS doctor" bash "$LEAF" doctor
  run_step "Runtime validation" bash "$LEAF" runtime validate
  run_step "Runtime selection" bash "$LEAF" runtime select
fi

real_args=(--profile "$PROFILE" --out-dir "$MODEL_REPORT_DIR" --max-workers "$MAX_WORKERS")
if [[ "$NO_ANIMATION" == "1" ]]; then real_args+=(--no-animation); fi
if [[ "$ALLOW_FALLBACK" == "1" ]]; then real_args+=(--allow-fallback); fi
if [[ "$CONTINUE_ON_ERROR" == "1" ]]; then real_args+=(--continue-on-error); fi
if [[ "$INCLUDE_EXPERIMENTAL" == "1" ]]; then real_args+=(--include-experimental); fi
if [[ -n "$CONFIRM_HEAVY" ]]; then real_args+=(--confirm-heavy "$CONFIRM_HEAVY"); fi
if [[ "$HASH_VERIFY" == "1" ]]; then real_args+=(--hash-verify); fi
if [[ -n "$MODEL_DIR" ]]; then real_args+=(--model-dir "$MODEL_DIR"); fi
if [[ "$YES" == "1" ]]; then real_args+=(--resolve --apply --yes); fi

run_step "Real model automation" bash "$REAL_MODELS" "${real_args[@]}"

cat > "$MANIFEST" <<EOF
{
  "schema_version": 1,
  "surface": "Bash-Version",
  "root": "$ROOT_DIR",
  "profile": "$PROFILE",
  "report_dir": "$REPORT_DIR",
  "model_report_dir": "$MODEL_REPORT_DIR",
  "runtime_role_policy_report": "$RUNTIME_ROLE_REPORT",
  "real_install_enabled": $([[ "$YES" == "1" ]] && printf true || printf false),
  "max_workers": "$MAX_WORKERS",
  "next_real_install_command": "bash install-real.sh --profile $PROFILE --yes"
}
EOF

if [[ "$YES" == "1" ]]; then
  printf '\n\033[32mLeafOS real installation automation finished.\033[0m\n'
else
  printf '\n\033[32mLeafOS real installation preview finished.\033[0m\n'
  printf 'Run this when ready to download/resume:\n'
  printf '  bash install-real.sh --profile %s --yes\n' "$PROFILE"
fi
printf 'manifest: %s\n' "$MANIFEST"
printf 'log:      %s\n' "$LOG"
