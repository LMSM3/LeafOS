#!/usr/bin/env bash
# tests/graph.sh — 0.3.0 graph layer smoke test
# Tests: graph_init, graph_add_node, graph_set_status, graph_next_ready,
#        graph_has_pending, brain_generate_graph, gate_run

set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export LEAF_ROOT="$ROOT_DIR"
export LEAF_ENABLE_TEST_MOCK_PROVIDER=1
export LEAF_BRAIN_PROVIDER=mock

source "$ROOT_DIR/core/brand/brand.sh"
source "$ROOT_DIR/core/graph/graph.sh"
source "$ROOT_DIR/core/model/brain.sh"
source "$ROOT_DIR/core/verify/gate.sh"

PASS=0
FAIL=0
TMPDIR_TEST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_TEST"' EXIT

_ok() {
	PASS=$(( PASS + 1 ))
	printf '  %s⚝%s  %s\n' "$C_GREEN_B" "$C_RESET" "$1"
}

_fail() {
	FAIL=$(( FAIL + 1 ))
	printf '  %s⚠︎%s  FAIL: %s\n' "$C_RED_B" "$C_RESET" "$1" >&2
}

_require() {
	local label="$1"; shift
	if "$@"; then _ok "$label"; else _fail "$label"; fi
}

brand_banner
brand_header "tests/graph.sh — 0.3.0 graph layer"
printf '\n'

# ---------------------------------------------------------------------------
GRAPH="$TMPDIR_TEST/test.graph.json"

# T1: graph_init creates a valid JSON file
brand_step 1 "graph_init"
graph_init "test goal" "$GRAPH" >/dev/null
_require "graph file exists"   test -f "$GRAPH"
_require "has nodes array"     bash -c "jq -e '.nodes | type == \"array\"' \"$GRAPH\" >/dev/null"
_require "correct version"     bash -c "jq -e '.leafos_graph_version == \"0.3.0\"' \"$GRAPH\" >/dev/null"
_require "correct goal"        bash -c "jq -e '.goal == \"test goal\"' \"$GRAPH\" >/dev/null"

# T2: graph_add_node appends a node
brand_step 2 "graph_add_node"
graph_add_node "$GRAPH" '{"id":"nodeA","type":"inspect","actor":"brain","status":"pending","depends_on":[],"weight":2.5,"inferred_model":"test-planner","quantization":"Q4_K_M","queued_at":"2026-07-17T12:00:00Z","input":{"task":"Inspect queue telemetry"}}'
graph_add_node "$GRAPH" '{"id":"nodeB","type":"write","status":"pending","depends_on":["nodeA"]}'
count="$(jq '.nodes | length' "$GRAPH")"
[[ "$count" -eq 2 ]] && _ok "2 nodes in graph" || _fail "expected 2 nodes, got $count"

# T2a: graph_queue_print keeps DATE as the rightmost heading and honors metadata
brand_step 2 "graph_queue_print"
queue_out="$(graph_queue_print "$GRAPH")"
grep -q '^  TASK.*DATE$' <<< "$queue_out" \
	&& _ok "queue DATE is rightmost heading" \
	|| _fail "queue DATE heading missing or misplaced"
grep -q 'Inspect queue telemetry.*2.50.*test-planner.*Q4_K_M.*2026-07-17T12:00:00Z' <<< "$queue_out" \
	&& _ok "queue renders task metadata" \
	|| _fail "queue metadata missing"

# T3: graph_node_status
brand_step 3 "graph_node_status"
st="$(graph_node_status "$GRAPH" nodeA)"
[[ "$st" == "pending" ]] && _ok "nodeA status=pending" || _fail "expected pending, got $st"

# T4: graph_next_ready — nodeA has no deps so it should be first
brand_step 4 "graph_next_ready"
nxt="$(graph_next_ready "$GRAPH")"
[[ "$nxt" == "nodeA" ]] && _ok "next ready = nodeA" || _fail "expected nodeA, got $nxt"

# T5: after marking nodeA done, nodeB becomes ready
brand_step 5 "graph_set_status + depends_on resolution"
graph_set_status "$GRAPH" nodeA done
nxt="$(graph_next_ready "$GRAPH")"
[[ "$nxt" == "nodeB" ]] && _ok "next ready = nodeB after nodeA done" || _fail "expected nodeB, got $nxt"

# T6: graph_has_pending
brand_step 6 "graph_has_pending"
graph_has_pending "$GRAPH" && _ok "has pending nodes" || _fail "should have pending"
graph_set_status "$GRAPH" nodeB done
graph_has_pending "$GRAPH" && _fail "should have no pending" || _ok "no pending nodes after all done"

# T7: brain_generate_graph from a real task file
brand_step 7 "brain_generate_graph"
TASK="$TMPDIR_TEST/test.task.md"
cat > "$TASK" <<'TASK'
# Build a shell calculator

## Scope
A POSIX shell calculator with add, sub, mul, div.

## Steps
- add main entry point
- add arithmetic functions
- write tests
TASK

BRAIN_GRAPH="$TMPDIR_TEST/brain.graph.json"
LEAF_RUNS_DIR="$TMPDIR_TEST"
out="$(brain_generate_graph "$TASK" "$BRAIN_GRAPH")"
_require "brain graph file exists"       test -f "$BRAIN_GRAPH"
_require "brain graph has nodes"         bash -c "jq -e '.nodes | length > 0' \"$BRAIN_GRAPH\" >/dev/null"
_require "brain graph has brain_inspect" bash -c "jq -e '[.nodes[] | select(.id==\"brain_inspect\")] | length > 0' \"$BRAIN_GRAPH\" >/dev/null"
_require "brain graph has verify node"   bash -c "jq -e '[.nodes[] | select(.id==\"verify\")] | length > 0' \"$BRAIN_GRAPH\" >/dev/null"
_require "brain graph has gate node"     bash -c "jq -e '[.nodes[] | select(.id==\"completion_gate\")] | length > 0' \"$BRAIN_GRAPH\" >/dev/null"
_require "brain graph queue metadata"    bash -c "jq -e 'all(.nodes[]; (.weight | type == \"number\") and (.inferred_model | type == \"string\") and (.quantization | type == \"string\") and (.queued_at | endswith(\"Z\")))' \"$BRAIN_GRAPH\" >/dev/null"
_require "coder node queue assignment"   bash -c "jq -e '[.nodes[] | select(.actor == \"coder\") | select(.weight == 2 and .inferred_model == \"gemma4-coder\" and .quantization == \"Q4_K_M\")] | length > 0' \"$BRAIN_GRAPH\" >/dev/null"

OFF_GRAPH="$TMPDIR_TEST/off.graph.json"
if LEAF_BRAIN_PROVIDER=off brain_generate_graph "$TASK" "$OFF_GRAPH" >/dev/null 2>&1; then
	_fail "brain should fail when provider is off"
else
	_ok "brain fails closed when provider is off"
fi
[[ ! -f "$OFF_GRAPH" ]] && _ok "disabled brain produced no graph" || _fail "disabled brain produced a graph"

# T8: gate_print does not crash
brand_step 8 "gate_print"
_require "gate_print runs" gate_print "$BRAIN_GRAPH"

# T9: gate_run on empty required_files/cmds passes
brand_step 9 "gate_run (empty gate)"
EMPTY_GATE_GRAPH="$TMPDIR_TEST/empty_gate.graph.json"
jq '.completion_gate = {required_files:[],required_commands:[],forbidden_paths:[]}' \
	"$BRAIN_GRAPH" > "$EMPTY_GATE_GRAPH"
_require "gate passes with empty checks" gate_run "$EMPTY_GATE_GRAPH" "$ROOT_DIR"

# ---------------------------------------------------------------------------
printf '\n'
brand_header "Results"
printf '  %s⚝ %d passed%s   %s⚠︎ %d failed%s\n\n' \
	"$C_GREEN_B" "$PASS" "$C_RESET" \
	"$C_RED_B"   "$FAIL" "$C_RESET"

if [[ $FAIL -eq 0 ]]; then
	brand_ok "tests/graph.sh PASSED"
	exit 0
else
	brand_warn "tests/graph.sh FAILED ($FAIL failures)"
	exit 1
fi
