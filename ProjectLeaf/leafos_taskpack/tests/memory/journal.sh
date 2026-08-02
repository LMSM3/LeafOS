#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
memory_bin="${LEAF_MEMORY_BIN:-$ROOT_DIR/build/leaf-memory}"
if [[ ! -x "$memory_bin" && -x "${memory_bin}.exe" ]]; then memory_bin="${memory_bin}.exe"; fi
[[ -x "$memory_bin" ]] || { printf 'memory test: executable not found: %s\n' "$memory_bin" >&2; exit 1; }
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
journal="$tmp_dir/memory.journal"
cp "$ROOT_DIR/tests/memory/fixtures/event.valid.json" "$tmp_dir/event.json"
"$memory_bin" append --journal "$journal" --event "$tmp_dir/event.json" | grep -q '"ok":true'
"$memory_bin" verify --journal "$journal" | grep -q '"records":1'
if "$memory_bin" append --journal "$journal" --event "$ROOT_DIR/tests/memory/fixtures/event.invalid-missing-integrity.json"; then
    printf 'memory test: invalid event was accepted\n' >&2
    exit 1
fi
size="$(wc -c < "$journal")"
dd if="$journal" of="$tmp_dir/truncated.journal" bs=1 count=$((size - 1)) status=none
if "$memory_bin" verify --journal "$tmp_dir/truncated.journal"; then
    printf 'memory test: truncated journal was accepted\n' >&2
    exit 1
fi
"$memory_bin" recover --journal "$tmp_dir/truncated.journal" | grep -q '"ok":true'
"$memory_bin" verify --journal "$tmp_dir/truncated.journal" | grep -q '"records":0'
printf 'memory journal test: PASS\n'
