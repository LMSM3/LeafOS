#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

bash "$ROOT_DIR/bin/leaf-overnight" validate >/dev/null
if bash "$ROOT_DIR/bin/leaf-overnight" validate --require-resolved >/dev/null 2>&1; then
	echo "unresolved medium-MoE template unexpectedly passed readiness" >&2
	exit 1
fi

python3 - "$ROOT_DIR/config/medium_moe_candidate.template.json" "$TMP_DIR/candidate.json" <<'PY'
import json
import sys

source, target = sys.argv[1:]
candidate = json.load(open(source, encoding="utf-8"))
candidate["status"] = "resolved"
candidate["identity"] = {
    "model_id": "fixture-moe-72b-a8b",
    "source_repo": "local/fixture-moe",
    "revision": "fixture-revision",
    "artifact": "fixture-moe-Q4_K_M.gguf",
    "sha256": "a" * 64,
    "license": "fixture-only",
}
candidate["topology"] = {
    "total_parameters_billion": 72,
    "active_parameters_billion": 8,
    "expert_count": 64,
    "active_experts_per_token": 8,
}
candidate["runtime"].update({
    "model_path": "/local/fixture-moe-Q4_K_M.gguf",
    "benchmark_command": ["llama-bench", "--model", "/local/fixture-moe-Q4_K_M.gguf"],
    "context_tokens": 8192,
    "gpu_layers": 999,
})
candidate["acceptance"] = {
    "minimum_generation_tokens_per_second": 1.0,
    "maximum_time_to_first_token_seconds": 60.0,
    "minimum_validated_useful_changes_per_hour": 0.0,
    "threshold_provenance": "Fixture thresholds fixed before the test run.",
}
with open(target, "w", encoding="utf-8") as handle:
    json.dump(candidate, handle, indent=2)
    handle.write("\n")
PY

bash "$ROOT_DIR/bin/leaf-overnight" --profile "$TMP_DIR/candidate.json" validate --require-resolved >/dev/null
bash "$ROOT_DIR/bin/leaf-overnight" --profile "$TMP_DIR/candidate.json" manifest \
	--mode leafos \
	--scenario resident_foreground \
	--duration-minutes 64 \
	--output "$TMP_DIR/manifest.json" >/dev/null
python3 - "$TMP_DIR/manifest.json" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
assert manifest["leafos_object"] == "medium_moe_benchmark_manifest"
assert manifest["candidate"]["identity"]["model_id"] == "fixture-moe-72b-a8b"
assert manifest["placement_truth"]["leafos_managed_ssd_tiering"] is False
assert manifest["safety"]["automatic_promotion"] is False
PY

python3 - "$ROOT_DIR/config/medium_moe_benchmark_metrics.sample.json" "$TMP_DIR/metrics.json" <<'PY'
import json
import sys

source, target = sys.argv[1:]
metrics = json.load(open(source, encoding="utf-8"))
metrics.update({
    "evidence_kind": "measured_local",
    "candidate_model_id": "fixture-moe-72b-a8b",
    "duration_minutes": 64,
    "scenario": "resident_foreground",
    "model_load_seconds": 10,
    "time_to_first_token_seconds": 2,
    "prompt_tokens_per_second": 40,
    "generation_tokens_per_second": 5,
    "gpu_process_alive_for_run": True,
    "provider_restarts": 0,
    "gpu_utilization_average_percent": 90,
    "gpu_vram_used_peak_percent": 90,
    "cpu_utilization_average_percent": 70,
    "ram_used_peak_percent": 90,
    "foreground_responsiveness_p95_ms": 150,
    "nvme_read_megabytes_per_second": 100,
    "major_page_faults": 0,
    "minor_page_faults": 10,
    "validated_patches": 1,
    "accepted_changes": 1,
    "rejected_changes": 0,
    "baseline_validation_passed": True,
    "oom_events": 0,
    "availability": {},
})
with open(target, "w", encoding="utf-8") as handle:
    json.dump(metrics, handle, indent=2)
    handle.write("\n")
PY

bash "$ROOT_DIR/bin/leaf-overnight" --profile "$TMP_DIR/candidate.json" evaluate \
	--mode leafos \
	--scenario resident_foreground \
	--duration-minutes 64 \
	--metrics "$TMP_DIR/metrics.json" \
	--output "$TMP_DIR/report.json" >/dev/null
python3 - "$TMP_DIR/report.json" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["leafos_object"] == "medium_moe_benchmark_report"
assert report["benchmark_passed"] is True
assert report["run_qualifies_for_portfolio"] is True
assert report["promotion_eligible"] is False
assert report["automatic_promotion"] is False
PY

echo "medium-MoE benchmark contract tests passed"
