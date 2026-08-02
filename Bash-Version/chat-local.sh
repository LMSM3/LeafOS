#!/usr/bin/env bash
# Start a simple local llama.cpp chat against the real LeafOS model cache.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$HERE/.." && pwd)"
INSTALLER="$ROOT_DIR/ProjectLeaf/leaf_model_installer"
DEFAULT_CACHE="$INSTALLER/models"
HOME_CACHE="$HOME/.leaf/models"
LLAMA_DIR="$ROOT_DIR/tmp/llama-cpp-ubuntu-x64-b9828/llama-b9828"
LLAMA="$LLAMA_DIR/llama-cli"

MODEL="opus"
MODEL_PATH=""
MODEL_DIR="${LEAF_MODEL_DIR:-}"
PROMPT=""
SYSTEM_PROMPT="You are LeafOS local runtime. Be concise, practical, and honest about uncertainty."
PROFILE="interactive"
PROFILES_FILE="$ROOT_DIR/ProjectLeaf/leafos_taskpack/config/runtime-profiles.json"
CTX=32768
THREADS=0
TOKENS=4096
TEMP=0.7
REASONING="auto"
REASONING_BUDGET=""
CTX_EXPLICIT=0
TOKENS_EXPLICIT=0

usage() {
  cat <<'EOF'
LeafOS local chat

Usage:
  bash chat-local.sh [--model opus|fable|qwen|qwopus] [--prompt TEXT]

Examples:
  bash chat-local.sh --model opus
  bash chat-local.sh --model fable --prompt "Write a tiny PowerShell hello-world."
  bash chat-local.sh --model qwen --prompt "Make a 3-step plan."

Model aliases:
  opus, assistant, main, scheduler      Gemma4 Opus Q4_K_M
  fable, coder, fable-q4, coder-q4      Gemma4 Fable Coder Q4_K_M
  fable-q2, fable-q3, fable-q6, fable-q8
  qwen, reasoning, oracle               Qwen Opus Reasoning MXFP4_MOE fallback
  qwopus, swift, secondary              Qwopus3.5 Coder Q4_K_M legacy optional

Options:
  --model-dir PATH       Override the model cache root
  --model-path PATH      Use an exact .gguf file
  --system TEXT          System prompt
  --profile NAME         Runtime profile: interactive|continual|overnight|compat-4k (default interactive)
  --ctx N                Context size (overrides profile)
  --threads N            CPU threads; 0 lets llama.cpp choose
  --tokens N             Maximum generated tokens (overrides profile)
  --temp N               Temperature
  --reasoning on|off|auto
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model|-m) MODEL="$2"; shift 2 ;;
    --model-dir) MODEL_DIR="$2"; shift 2 ;;
    --model-path) MODEL_PATH="$2"; shift 2 ;;
    --prompt|-p) PROMPT="$2"; shift 2 ;;
    --system|--system-prompt) SYSTEM_PROMPT="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --ctx|-c) CTX="$2"; CTX_EXPLICIT=1; shift 2 ;;
    --threads|-t) THREADS="$2"; shift 2 ;;
    --tokens|-n) TOKENS="$2"; TOKENS_EXPLICIT=1; shift 2 ;;
    --temp|--temperature) TEMP="$2"; shift 2 ;;
    --reasoning) REASONING="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) printf 'unknown chat-local option: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

normalize_path() {
  local path="$1"
  if command -v wslpath >/dev/null 2>&1 && [[ "$path" =~ ^[A-Za-z]:\\ ]]; then
    wslpath -a "$path"
  else
    printf '%s\n' "$path"
  fi
}

if [[ -z "$MODEL_DIR" ]]; then
  if [[ -d "$DEFAULT_CACHE" ]] && find "$DEFAULT_CACHE" -type f -name '*.gguf' -print -quit 2>/dev/null | grep -q .; then
    MODEL_DIR="$DEFAULT_CACHE"
  else
    MODEL_DIR="$HOME_CACHE"
  fi
fi

MODEL_DIR="$(normalize_path "$MODEL_DIR")"
if [[ -n "$MODEL_PATH" ]]; then
  MODEL_PATH="$(normalize_path "$MODEL_PATH")"
else
  case "${MODEL,,}" in
    opus|assistant|main|scheduler|sage)
      MODEL_PATH="$MODEL_DIR/Gemma4-Opus-Assistant/gemma4-opus48-Q4_K_M.gguf"
      ;;
    fable|coder|forge|fable-q4|coder-q4|gemma4-coder)
      MODEL_PATH="$MODEL_DIR/Gemma4-Coder/gemma4-coding-Q4_K_M.gguf"
      ;;
    fable-q2|coder-q2)
      MODEL_PATH="$MODEL_DIR/Gemma4-Coder/gemma4-coding-Q2_K.gguf"
      ;;
    fable-q3|coder-q3)
      MODEL_PATH="$MODEL_DIR/Gemma4-Coder/gemma4-coding-Q3_K_M.gguf"
      ;;
    fable-q6|coder-q6)
      MODEL_PATH="$MODEL_DIR/Gemma4-Coder/gemma4-coding-Q6_K.gguf"
      ;;
    fable-q8|coder-q8)
      MODEL_PATH="$MODEL_DIR/Gemma4-Coder/gemma4-coding-Q8_0.gguf"
      ;;
    qwen|reasoning|oracle|scheduler-fallback)
      MODEL_PATH="$MODEL_DIR/Qwen3.5-Claude-Reasoning/Qwen3.5-14B-A3B-Claude-Opus-Reasoning-Distilled-4.6-MXFP4_MOE.gguf"
      ;;
    qwopus|swift|secondary|legacy-coder)
      MODEL_PATH="$MODEL_DIR/Qwopus3.5-9B-Coder-MTP/Qwopus3.5-9B-Coder-MTP-Q4_K_M.gguf"
      ;;
    *)
      printf 'unknown model alias: %s\n\n' "$MODEL" >&2
      usage >&2
      exit 2
      ;;
  esac
fi

# Resolve context/token/reasoning budget from the named runtime profile unless
# the caller explicitly overrode --ctx/--tokens. Command-line overrides always
# win per the documented precedence: cli > profile > provider limit > model
# metadata > compat-4k default.
#
# WO-019 019-A / Gate G2: this MUST delegate to the single canonical resolver
# (core/runtime/profile_resolver.py) rather than re-implement resolution
# logic inline, so that Bash and PowerShell produce byte-equivalent JSON.
RESOLVER_SCRIPT="$ROOT_DIR/ProjectLeaf/leafos_taskpack/core/runtime/profile_resolver.py"
CAPABILITY_MANIFEST=""
if [[ -f "$PROFILES_FILE" ]] && [[ -f "$RESOLVER_SCRIPT" ]] && command -v python3 >/dev/null 2>&1; then
  resolver_args=(--profiles-file "$PROFILES_FILE" --profile "$PROFILE" --provider llama.cpp)
  [[ -n "$MODEL_PATH" ]] && resolver_args+=(--model "$MODEL_PATH")
  [[ "$CTX_EXPLICIT" == "1" ]] && resolver_args+=(--ctx "$CTX")
  [[ "$TOKENS_EXPLICIT" == "1" ]] && resolver_args+=(--tokens "$TOKENS")

  manifest_json="$(python3 "$RESOLVER_SCRIPT" "${resolver_args[@]}")"
  if ! printf '%s' "$manifest_json" | grep -q '"error"'; then
    CAPABILITY_MANIFEST="$manifest_json"
    CTX="$(printf '%s' "$manifest_json" | python3 -c 'import json,sys;print(json.load(sys.stdin)["context_limit"])')"
    TOKENS="$(printf '%s' "$manifest_json" | python3 -c 'import json,sys;print(json.load(sys.stdin)["max_output_tokens"])')"
    REASONING_BUDGET="$(printf '%s' "$manifest_json" | python3 -c 'import json,sys;print(json.load(sys.stdin)["reasoning_budget_requested"])')"
    if [[ "$PROFILE" == "compat-4k" ]]; then
      REASONING="off"
    fi
  else
    printf 'warning: runtime profile "%s" unavailable, using explicit/default values\n' "$PROFILE" >&2
  fi
fi

if [[ ! -x "$LLAMA" ]]; then
  printf 'llama.cpp chat binary not found: %s\n' "$LLAMA" >&2
  exit 2
fi

if [[ ! -f "$MODEL_PATH" ]]; then
  printf 'model file not found: %s\n' "$MODEL_PATH" >&2
  printf 'Run a status check first: bash real-models.sh --profile runtime-default --status-only\n' >&2
  exit 1
fi

export LD_LIBRARY_PATH="$LLAMA_DIR${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

printf '\033[36mLeafOS local chat\033[0m\n'
printf 'model: %s\n' "$MODEL_PATH"
if [[ -z "$PROMPT" ]]; then
  printf 'mode:  interactive conversation. Press Ctrl+C to leave.\n\n'
else
  printf 'mode:  single turn\n\n'
fi

cmd=(
  "$LLAMA"
  -m "$MODEL_PATH"
  -c "$CTX"
  -n "$TOKENS"
  --temp "$TEMP"
  -cnv
  --simple-io
  --no-display-prompt
  --no-show-timings
  --no-warmup
  -rea "$REASONING"
  -sys "$SYSTEM_PROMPT"
)

if [[ "$REASONING" == "off" ]]; then
  cmd+=(--reasoning-budget 0)
elif [[ -n "$REASONING_BUDGET" && "$REASONING_BUDGET" != "0" ]]; then
  cmd+=(--reasoning-budget "$REASONING_BUDGET")
fi

if [[ "$THREADS" != "0" ]]; then
  cmd+=(--threads "$THREADS")
fi

if [[ -n "$PROMPT" ]]; then
  cmd+=(-st -p "$PROMPT")
fi

exec "${cmd[@]}"
