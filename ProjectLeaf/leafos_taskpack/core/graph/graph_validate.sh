#!/usr/bin/env bash
# core/graph/graph_validate.sh  --  Hardened graph validation (WO-007-C §3)
#
# graph_validate GRAPH_FILE [ROOT_DIR]
#
# Rules enforced (all fail-closed):
#   - Valid JSON
#   - Contains LEAFOS_AGENT_PLAN=1 (checked in source script, embedded in graph goal)
#   - Only allow-listed node types
#   - Node count <= LEAF_GRAPH_MAX_NODES (default 64)
#   - No cycles (DAG check via jq topological sort)
#   - All node paths normalized + confined to ROOT_DIR
#   - No symlinks escaping ROOT_DIR
#   - No writes to protected paths (.git/, secrets, env files)
#   - Unknown fields do not block (warn-only) -- fail on semantic violations
#
# Exit codes (Appendix B): 0=ok, 1=validation failed, 3=prereq missing

set -uo pipefail

_GV_ROOT="${_GV_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
source "$_GV_ROOT/core/brand/brand.sh"

LEAF_GRAPH_MAX_NODES="${LEAF_GRAPH_MAX_NODES:-64}"

# Allow-listed node types (WO-007-C §3.3)
# Grows by human decision only.
[[ -v _GV_ALLOWED_TYPES ]] || readonly _GV_ALLOWED_TYPES="write_file write_patch read_file run_test summarize wait_for_user inspect write verify gate report plan repair"

# Protected path prefixes — no node may write to these
[[ -v _GV_PROTECTED ]] || readonly _GV_PROTECTED=".git/ .env .env. secrets/ credentials/ id_rsa id_ed25519"

# ---------------------------------------------------------------------------
# graph_validate GRAPH_FILE [ROOT_DIR]
# Returns 0 on pass, 1 on any violation, 3 on missing prereq.
# Prints one line per check: [ok] / [fail] RULE: details
# ---------------------------------------------------------------------------
graph_validate() {
	local graph="${1:-}"
	local root="${2:-$_GV_ROOT}"
	local fail=0

	# -- Prereq: jq -----------------------------------------------------------
	command -v jq &>/dev/null || {
		brand_warn "graph_validate: jq is required"
		return 3
	}

	[[ -f "$graph" ]] || {
		_gv_fail "file exists" "not found: $graph"
		return 1
	}

	# -- Rule 1: valid JSON ---------------------------------------------------
	if ! jq empty "$graph" 2>/dev/null; then
		_gv_fail "valid JSON" "file is not valid JSON: $graph"
		return 1
	fi
	_gv_ok "valid JSON"

	# -- Rule 2: node count ---------------------------------------------------
	local count
	count="$(jq '.nodes | length' "$graph" 2>/dev/null)"
	if (( count > LEAF_GRAPH_MAX_NODES )); then
		_gv_fail "node count" "${count} nodes exceeds limit ${LEAF_GRAPH_MAX_NODES}"
		(( fail++ ))
	else
		_gv_ok "node count" "${count} nodes (limit: ${LEAF_GRAPH_MAX_NODES})"
	fi

	# -- Rule 3: allowed node types -------------------------------------------
	local bad_types
	bad_types="$(jq -r '.nodes[].type // empty' "$graph" 2>/dev/null | sort -u | while IFS= read -r t; do
		found=0
		for allowed in $_GV_ALLOWED_TYPES; do
			[[ "$t" == "$allowed" ]] && found=1 && break
		done
		[[ $found -eq 0 ]] && printf '%s\n' "$t"
	done)"
	if [[ -n "$bad_types" ]]; then
		while IFS= read -r bt; do
			_gv_fail "allowed node type" "rejected type: '$bt' -- not in allow-list"
			(( fail++ ))
		done <<< "$bad_types"
	else
		_gv_ok "allowed node types"
	fi

	# -- Rule 4: no cycles (DAG check) ----------------------------------------
	# Build adjacency and detect cycles via DFS using jq + bash
	local cycle_result
	cycle_result="$(jq -r '
		.nodes | to_entries |
		map(.value | {id: .id, deps: (.depends_on // [])}) |
		# emit "id dep" pairs for each dependency
		.[] | .id as $id | .deps[] | "\($id) \(.)"
	' "$graph" 2>/dev/null | python3 -c "
import sys
edges = []
nodes = set()
for line in sys.stdin:
	line = line.strip()
	if not line: continue
	parts = line.split()
	if len(parts) == 2:
		edges.append((parts[0], parts[1]))
		nodes.update(parts)

# Kahn's algorithm
from collections import defaultdict, deque
in_deg = defaultdict(int)
adj = defaultdict(list)
for u,v in edges:
	adj[u].append(v)
	in_deg[v] += 1
	in_deg.setdefault(u, 0)

q = deque(n for n in nodes if in_deg[n] == 0)
visited = 0
while q:
	n = q.popleft()
	visited += 1
	for nb in adj[n]:
		in_deg[nb] -= 1
		if in_deg[nb] == 0:
			q.append(nb)

if visited < len(nodes):
	cycle_nodes = [n for n in nodes if in_deg[n] > 0]
	print('cycle: ' + ', '.join(sorted(cycle_nodes)))
else:
	print('ok')
" 2>/dev/null || echo "check_failed")"

	case "$cycle_result" in
		ok)
			_gv_ok "no cycles (DAG)"
			;;
		check_failed)
			_gv_fail "no cycles (DAG)" "cycle check failed (python3 required)"
			(( fail++ ))
			;;
		*)
			_gv_fail "no cycles (DAG)" "$cycle_result"
			(( fail++ ))
			;;
	esac

	# -- Rule 5: path confinement ---------------------------------------------
	# Normalize every path-like field in node inputs; assert under root
	local root_real; root_real="$(cd "$root" && pwd)"
	local bad_paths=0

	while IFS= read -r raw_path; do
		[[ -z "$raw_path" ]] && continue
		# Resolve relative to root; strip leading slash from relative paths
		local norm
		if [[ "$raw_path" == /* ]]; then
			norm="$(python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$raw_path" 2>/dev/null || echo "$raw_path")"
		else
			norm="$(python3 -c "import os,sys; print(os.path.realpath(os.path.join(sys.argv[1],sys.argv[2])))" "$root_real" "$raw_path" 2>/dev/null || echo "$root_real/$raw_path")"
		fi
		# Must start with root_real
		if [[ "$norm" != "$root_real"* ]]; then
			_gv_fail "path confinement" "escapes root: '$raw_path' -> '$norm'"
			(( fail++ )); (( bad_paths++ ))
		fi
		# Check protected prefixes
		local rel="${norm#$root_real/}"
		for prot in $_GV_PROTECTED; do
			if [[ "$rel" == "$prot"* ]]; then
				_gv_fail "protected path" "writes to protected: '$rel'"
				(( fail++ )); (( bad_paths++ ))
				break
			fi
		done
	done < <(jq -r '.nodes[].input | to_entries[]? | .value | select(type=="string") | select(startswith(".") or startswith("/") or contains("/"))' "$graph" 2>/dev/null)

	[[ $bad_paths -eq 0 ]] && _gv_ok "path confinement"

	# -- Rule 6: no shell execution from model text ---------------------------
	# Nodes must not have type "shell" or action "shell.exec" / "shell.run" on a write node
	local shell_violations
	shell_violations="$(jq -r '.nodes[] | select(.type=="write" or .type=="write_file" or .type=="write_patch") | select(.action=="shell.run" or .action=="shell.exec") | .id' "$graph" 2>/dev/null)"
	if [[ -n "$shell_violations" ]]; then
		while IFS= read -r vid; do
			_gv_fail "no shell exec on write nodes" "node '$vid' combines write type with shell action"
			(( fail++ ))
		done <<< "$shell_violations"
	else
		_gv_ok "no shell exec on write nodes"
	fi

	# -- Result ---------------------------------------------------------------
	if [[ $fail -eq 0 ]]; then
		brand_ok "graph validated: $graph"
		return 0
	else
		brand_warn "graph validation failed: $fail violation(s) in $graph"
		return 1
	fi
}

_gv_ok() {
	local rule="$1" detail="${2:-}"
	printf '  [ok]   %s' "$rule"
	[[ -n "$detail" ]] && printf '  (%s)' "$detail"
	printf '\n'
}

_gv_fail() {
	local rule="$1" detail="${2:-}"
	printf '  [fail] %s' "$rule"
	[[ -n "$detail" ]] && printf '  -- %s' "$detail"
	printf '\n'
}
