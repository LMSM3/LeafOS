#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

payload="$("$ROOT_DIR/bin/leafctl" fullstackbench --json --generated-tokens 8 --rounds 1 --work 20 --no-gpu)"

printf '%s' "$payload" | jq -e '
    .leafos_object == "fullstackbench"
    and .runner.name == "raw_token_pump"
    and .runner.real_model_inference == false
    and .safety.downloads_model_weights == false
    and .stack.action_model.key == "gemma4-coder"
    and (.quantization | length) >= 5
    and all(.quantization[]; .prompt_tk_s > 0 and .generation_tk_s > 0 and .total_tk_s > 0)
' >/dev/null

echo "fullstackbench tests passed"

# Real measurement cell 2: hold one llama.cpp conversation open for 60 seconds.
conversation="$($ROOT_DIR/bin/leafctl realbench conversation --duration 60 --interval 5)"
printf '%s' "$conversation" | jq -e '
    .runner == "llama-cli"
    and .requested_duration_seconds == 60
    and .duration_met == true
    and .turns_sent > 0
' >/dev/null

echo "real 60-second conversation test passed"

# Real measurement cell 3: isolate decode throughput and report the 66 tk/s target.
throughput="$($ROOT_DIR/bin/leafctl realbench raw --target 66)"
printf '%s' "$throughput" | jq -e '
    .runner == "llama-bench"
    and .target_tk_s == 66
    and .generation_tk_s > 0
    and (.target_met == true or .target_met == false)
' >/dev/null

echo "real raw tk/s benchmark recorded (target: 66 tk/s)"
