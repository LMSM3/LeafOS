#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ "${1:-}" == "validate-root" ]]; then
	python3 - "$ROOT_DIR" <<'PY'
import json
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
	metadata["source_tree"],
	metadata["configuration_authorities"]["runtime"],
	metadata["configuration_authorities"]["providers"],
]
missing = [path for path in paths if not (root / path).exists()]
if missing:
	raise SystemExit("Root contract target is missing: " + ", ".join(missing))
print(json.dumps({"status": "passed", "schema_version": metadata["schema_version"]}))
PY
	exit 0
fi

exec bash "$ROOT_DIR/Bash-Version/leaf.sh" "$@"
