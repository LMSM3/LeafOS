#!/usr/bin/env bash
set -euo pipefail

# Compatibility wrapper for local-only dependency checks and offline planning.
slot=1
quant=""
dest="${LEAF_MODEL_DIR:-$HOME/.leaf/models}"
plan="./leaf-model-plan.json"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --slot) slot="${2:?missing slot}"; shift 2 ;;
    --quant) quant="${2:?missing quant}"; shift 2 ;;
    --dest) dest="${2:?missing destination}"; shift 2 ;;
    --plan) plan="${2:?missing plan path}"; shift 2 ;;
    -h|--help)
      printf 'Usage: system-preflight.sh [--slot 1-5] [--quant QUANT] [--dest DIR] [--plan FILE]\n'
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
"$launcher" doctor
args=(plan --slot "$slot" --dest "$dest" --out "$plan")
[[ -n "$quant" ]] && args+=(--quant "$slot=$quant")
exec "$launcher" "${args[@]}"

# Legacy implementation below is unreachable and retained for migration history.

model="gemma4-coder"
quant="Q4_K_M"
dest="./models"
wait_seconds=12
flush_dns=0

fail() {
  printf 'PREFLIGHT FAILED: %s\n' "$1" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model) model="${2:-}"; shift 2 ;;
    --quant) quant="${2:-}"; shift 2 ;;
    --dest) dest="${2:-}"; shift 2 ;;
    --wait-seconds) wait_seconds="${2:-}"; shift 2 ;;
    --flush-dns) flush_dns=1; shift ;;
    -h|--help)
      cat <<'HELP'
Usage: ./shell_helpers/system-preflight.sh [--model gemma4-coder|qwen-opus-reasoning] [--quant Q4_K_M] [--dest ./models] [--wait-seconds 12] [--flush-dns]
Shell fallback preflight: system info, NVIDIA/RAM scan, loading animation, optional DNS flush, and explicit target report.
HELP
      exit 0 ;;
    *) fail "Unknown argument: $1" ;;
  esac
done

case "$model" in
  gemma4-coder) local_dir="Gemma4-Coder" ;;
  qwen-opus-reasoning) local_dir="Qwen3.5-Claude-Reasoning" ;;
  *) fail "Unknown model: $model" ;;
esac

mkdir -p "$dest"
target="$(cd "$dest" && pwd)/$local_dir"
mkdir -p "$target"

printf '☠ Leaf Model Puller v0.3.0 preflight\n'
printf 'System: %s %s %s\n' "$(uname -s)" "$(uname -r)" "$(uname -m)"
printf 'Target download directory: %s\n' "$target"

printf 'NVIDIA SMI:\n'
gpu_json='[]'
max_vram_gb=0
if command -v nvidia-smi >/dev/null 2>&1; then
  raw_gpu="$(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader,nounits || true)"
  if [[ -n "$raw_gpu" ]]; then
    printf '%s\n' "$raw_gpu" | while IFS= read -r line; do printf '%s MB\n' "$line"; done
    max_vram_mb="$(printf '%s\n' "$raw_gpu" | awk -F',' '{gsub(/ /,"",$3); if ($3>m) m=$3} END{print m+0}')"
    max_vram_gb="$(awk -v mb="$max_vram_mb" 'BEGIN { printf "%.2f", mb / 1024 }')"
  fi
else
  printf 'NVIDIA SMI not found.\n'
fi

ram_total_gb=0
if [[ -r /proc/meminfo ]]; then
  ram_total_gb="$(awk '/MemTotal/ { printf "%.2f", $2 / 1024 / 1024 }' /proc/meminfo)"
elif command -v sysctl >/dev/null 2>&1; then
  ram_bytes="$(sysctl -n hw.memsize 2>/dev/null || printf 0)"
  ram_total_gb="$(awk -v b="$ram_bytes" 'BEGIN { printf "%.2f", b / 1024 / 1024 / 1024 }')"
fi
printf 'RAM: total %s GB\n' "$ram_total_gb"

if awk -v s="$wait_seconds" 'BEGIN { exit !(s > 0) }'; then
  frames=( '𒅒' '𒈔' '𒅒' '𒇫' '𒄆' )
  start="$(date +%s)"
  i=0
  while true; do
    now="$(date +%s)"
    elapsed=$((now - start))
    [[ "$elapsed" -ge "${wait_seconds%.*}" ]] && break
    frame="${frames[$((i % ${#frames[@]}))]}"
    printf '\rLoading... %s  %ss' "$frame" "$elapsed"
    sleep 0.2
    i=$((i + 1))
  done
  printf '\rLoading complete. No success implied.          \n'
fi

dns_success=true
dns_messages=""
if [[ "$flush_dns" -eq 1 ]]; then
  if command -v resolvectl >/dev/null 2>&1; then
    resolvectl flush-caches || dns_success=false
  elif command -v systemd-resolve >/dev/null 2>&1; then
    systemd-resolve --flush-caches || dns_success=false
  elif command -v dscacheutil >/dev/null 2>&1; then
    dscacheutil -flushcache || dns_success=false
    killall -HUP mDNSResponder 2>/dev/null || true
  else
    dns_success=false
    dns_messages="No standard DNS flush command found."
  fi
  [[ "$dns_success" == true ]] || fail "DNS flush was requested and did not complete. $dns_messages"
fi

recommend="Q2_K"
reason="Very limited detected memory; smallest option."
if [[ "$model" == "qwen-opus-reasoning" ]]; then
  recommend=""
  reason="This model entry pulls all matching GGUF files; no quant selector is used."
elif awk -v v="$max_vram_gb" -v r="$ram_total_gb" 'BEGIN{exit !((v>=15)||(r>=48))}'; then
  recommend="Q8_0"; reason="Enough detected memory for the largest listed file with headroom."
elif awk -v v="$max_vram_gb" -v r="$ram_total_gb" 'BEGIN{exit !((v>=11.5)||(r>=32))}'; then
  recommend="Q6_K"; reason="Enough detected memory for a higher-quality quant with some margin."
elif awk -v v="$max_vram_gb" -v r="$ram_total_gb" 'BEGIN{exit !((v>=8)||(r>=16))}'; then
  recommend="Q4_K_M"; reason="Recommended baseline for sane local use."
elif awk -v v="$max_vram_gb" -v r="$ram_total_gb" 'BEGIN{exit !((v>=6.5)||(r>=12))}'; then
  recommend="Q3_K_M"; reason="Memory looks tight for the baseline; cautious fallback."
fi

manifest="$target/leaf_preflight_report.json"
cat > "$manifest" <<JSON
{
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "model": "$model",
  "requested_quant": "$quant",
  "destination_root": "$(cd "$dest" && pwd)",
  "target_dir": "$target",
  "ram_total_gb": $ram_total_gb,
  "max_vram_gb": $max_vram_gb,
  "dns_flush_requested": $([[ "$flush_dns" -eq 1 ]] && echo true || echo false),
  "dns_flush_success": $dns_success,
  "recommendation": {
    "recommended_quant": "${recommend}",
    "reason": "${reason}"
  }
}
JSON

printf 'Recommended quant: %s\n' "${recommend:-not applicable}"
printf 'Reason: %s\n' "$reason"
printf 'Preflight report: %s\n' "$manifest"
printf 'PREFLIGHT COMPLETE. No model download has been claimed.\n'
