#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "validate-root" ]]; then
	if command -v python3 >/dev/null 2>&1; then
		PYTHON_BIN=python3
	elif command -v python >/dev/null 2>&1; then
		PYTHON_BIN=python
	else
		printf '%s\n' 'leafos: validate-root needs Python 3 on PATH.' >&2
		exit 127
	fi
	"$PYTHON_BIN" - "$ROOT_DIR" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
metadata = json.loads((root / "leafos.root.json").read_text(encoding="utf-8"))
paths = [
	metadata["documentation"]["primary_reference"],
	metadata["documentation"]["primary_reference_tex"],
	metadata["documentation"]["product_map"],
	metadata["documentation"]["usage"],
	metadata["documentation"]["installation"],
	metadata["documentation"]["root_contract"],
	metadata["surfaces"]["powershell"]["directory"],
	metadata["surfaces"]["bash"]["directory"],
	metadata["program"]["powershell"],
	metadata["program"]["bash"],
	metadata["program"]["implementation"],
	metadata["program"]["immutable_brand_manifest"],
	metadata["change_loop"]["ccis_cli"],
	metadata["change_loop"]["scientific_loop"],
	metadata["change_loop"]["typed_task_registry"],
	metadata["change_loop"]["series_index"],
	metadata["change_loop"]["next_work_order"],
	"VERSION",
	"ProjectLeaf/leafos_taskpack/VERSION",
	metadata["source_tree"],
	metadata["configuration_authorities"]["runtime"],
	metadata["configuration_authorities"]["providers"],
]
missing = [path for path in paths if not (root / path).exists()]
if missing:
	raise SystemExit("Root contract target is missing: " + ", ".join(missing))

root_version = (root / "VERSION").read_text(encoding="utf-8").strip()
taskpack_version = (root / "ProjectLeaf/leafos_taskpack/VERSION").read_text(encoding="utf-8").strip()
if not re.fullmatch(r"\d+\.\d+\.\d+", root_version):
	raise SystemExit("Root VERSION is not numeric semantic versioning: " + root_version)
if not (root_version == taskpack_version == str(metadata["version"])):
	raise SystemExit(
		"Version authorities disagree: "
		+ json.dumps({"root": root_version, "taskpack": taskpack_version, "metadata": metadata["version"]})
	)
if tuple(map(int, root_version.split("."))) < (0, 2, 2):
	raise SystemExit("LeafOS version must not be older than the normalized 0.2.2 baseline")

task_registry = json.loads(
	(root / metadata["change_loop"]["typed_task_registry"]).read_text(encoding="utf-8")
)
registered = {
	(item.get("task_type"), item.get("task_version"))
	for item in task_registry.get("entries", [])
}
required_loop_tasks = {
	("probe.llamacpp.capability", 1),
	("eval.llamacpp.grammar", 1),
	("eval.llamacpp.stream", 1),
}
missing_loop_tasks = sorted(required_loop_tasks - registered)
if missing_loop_tasks:
	raise SystemExit("Typed change-loop registry is missing: " + repr(missing_loop_tasks))

manifest_path = root / metadata["program"]["immutable_brand_manifest"]
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if manifest.get("immutable") is not True:
	raise SystemExit("Brand asset manifest is not marked immutable")
asset = (root / manifest["path"]).resolve()
try:
	asset.relative_to(root.resolve())
except ValueError as exc:
	raise SystemExit("Immutable asset escapes the LeafOS root") from exc
if not asset.is_file():
	raise SystemExit("Immutable asset is missing: " + manifest["path"])
digest = hashlib.sha256(asset.read_bytes()).hexdigest()
if digest.lower() != str(manifest["sha256"]).lower() or asset.stat().st_size != int(manifest["bytes"]):
	raise SystemExit("Immutable asset verification failed: " + manifest["path"])
readme = (root / "README.md").read_text(encoding="utf-8")
if manifest["path"] not in readme or "leafos-program:brand-asset:start" not in readme:
	raise SystemExit("Root README does not reference the immutable asset")

print(json.dumps({
	"status": "passed",
	"schema_version": metadata["schema_version"],
	"version": root_version,
	"asset_verified": True,
	"change_loop": "ccis",
}))
PY
	exit 0
fi

exec bash "$ROOT_DIR/Bash-Version/leaf.sh" "$@"
