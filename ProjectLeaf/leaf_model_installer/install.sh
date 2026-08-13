#!/usr/bin/env bash
# Bootstrap tooling only. Model transfers require a later explicit `leaf-models apply`.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || {
  printf 'INSTALL FAILED: Python 3.9+ was not found.\n' >&2
  exit 1
}

candidate=".venv.next.$$"
backup_root=".backups"
cleanup() {
  [[ -d "$candidate" ]] && rm -rf -- "$candidate"
}
trap cleanup EXIT

"$PYTHON_BIN" -m venv "$candidate"
"$candidate/bin/python" -m pip install --upgrade pip
"$candidate/bin/python" -m pip install .
"$candidate/bin/python" -m leaf_models.install_cli doctor

mkdir -p "$backup_root"
if [[ -d .venv ]]; then
  mv .venv "$backup_root/.venv.$(date +%Y%m%d-%H%M%S)"
fi
mv "$candidate" .venv

cat > leaf-models <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/.venv/bin/python" -m leaf_models.install_cli "$@"
LAUNCHER
chmod +x leaf-models

printf 'Installer tooling is ready. No model download was started.\n'
printf 'Catalog: ./leaf-models catalog\n'
printf 'Plan:    ./leaf-models plan --profile default\n'
