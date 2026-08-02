# LeafOS-WO-020 — Game Logic Improvement

**Status:** Partial  
**Priority:** High  
**Target:** `C:\R\LeafOS0.2.1\ProjectLeaf`  
**Primary system:** `board-game-lab` / Catan2 benchmark  
**Execution model:** Local-only, deterministic-first, checkpointed  
**Authority model:** CPU-validated state; GPU/LLM proposals remain advisory  

## 0. Current Status

[W] WO-020: Game logic improvement / spatial board substrate  
[D] Day unassigned: pre-LLM game-logic slice  
[I] PARTIAL: GLI-02 topology implemented; Catan2 buildings now derive productive tiles from vertex incidence  
[V] PASS: Python compile, board-spatial unittest, Catan2 shell smoke, PowerShell Catan2 smoke  
[P] LOCAL: canonical clone `C:\R\LeafOS0.2.1\ProjectLeaf\leafos_taskpack`  
[N] Next: GLI-03 piece model and occupancy validation, then robber/road rule fixtures  

## 1. Mission

Replace the present flat Catan2 resource-selection model with a general board-spatial logic layer capable of representing:

- tile-to-tile adjacency and interaction;
- vertices, edges, regions, boundaries, and connectivity;
- settlements, cities, roads, blockers, tokens, and movable physical pieces;
- continuous or discrete spatial position and orientation;
- logical state separated from observed physical state;
- uncertain physical observations followed by deterministic reconciliation;
- structured event output for the LeafOS scheduler and full-screen terminal interface;
- deterministic replay, evidence capture, and CPU-authoritative validation.

The immediate demonstration target is Catan2. The resulting spatial kernel must not depend on Catan-specific rules and must be usable by later board-game adapters.

## 2. Baseline and Problem Statement

The current Catan2 benchmark correctly defines a fixed tile catalog, player buildings, continual harvesting, deterministic bots, and optional GPU/CPU brain hooks. It does not yet contain a spatial board model.

Current limitations:

1. `Tile` records contain no coordinates or neighbor relationships.
2. `Building` records copy adjacent tile identifiers instead of occupying a board vertex.
3. Roads, ports, edges, intersections, regions, and route connectivity are absent.
4. A physical piece cannot be moved, rotated, stacked, misplaced, or observed with uncertainty.
5. Tile effects cannot propagate to neighboring tiles.
6. Logical state and physical observation are not separated.
7. Brain commands may return loosely parsed text instead of a strict decision record.
8. Blocking child commands can freeze the benchmark, scheduler, and future TUI.
9. The benchmark emits insufficient structured evidence for spatial replay and inspection.

The required improvement is not merely more Catan rules. It is a board-world representation beneath individual game rules.

## 3. Design Principle

Represent a board as a typed spatial complex:

\[
\mathcal{B}=(T,V,E,P,R)
\]

where:

- \(T\) is the set of tiles or regions;
- \(V\) is the set of vertices or placement points;
- \(E\) is the set of edges, paths, or boundaries;
- \(P\) is the set of physical or logical pieces;
- \(R\) is the set of typed relations, including adjacency, incidence, occupancy, blocking, visibility, and ownership.

Game rules consume this representation. They must not redefine its geometry.

## 4. Scope

### 4.1 In Scope

- Generic two-dimensional board geometry.
- Axial-coordinate hex tiles.
- Derived tile, vertex, and edge topology.
- Logical anchors for tile-, vertex-, and edge-bound pieces.
- Piece pose, footprint, orientation, ownership, and confidence.
- Pairwise tile interactions and neighborhood propagation.
- Catan2 settlements, cities, roads, robber, number tokens, and movable tiles.
- Legal-placement and occupancy validation.
- Physical-observation ingestion through a provider-neutral record.
- Observation-to-anchor snapping and ambiguity reporting.
- Strict local brain-command protocol with timeout and fallback.
- JSONL event output and atomic checkpoints.
- TUI panels and controls for spatial state.
- Deterministic replay and conformance tests.

### 4.2 Out of Scope for This Work Order

- A complete implementation of official commercial Catan rules.
- Camera drivers or vendor-specific sensor integration.
- Computer-vision model training.
- Full rigid-body dynamics, friction, or piece deformation.
- Networked multiplayer.
- Remote inference providers.
- Photorealistic three-dimensional rendering.
- Autonomous robotic piece manipulation.

Physical support in this work order means geometry, observations, uncertainty, anchoring, occupancy, and reconciliation. It does not mean simulating every tragic wobble of a wooden road.

## 5. Required Architecture

```text
PowerShell / Windows Terminal
        |
        v
Full-screen LeafOS TUI
        |
        v
Session controller and worker process
        |------------------------------|
        v                              v
vulkan-provider.ps1             catan2_benchmark.exe
        |                              |
        v                              v
Local llama.cpp provider        Board-spatial kernel
                                       |
                                       v
                              Catan2 rule adapter
                                       |
                                       v
                         JSONL events + checkpoints
```

The TUI is the control plane. The C benchmark is a worker. The provider script owns local model process configuration. The spatial kernel owns geometry and occupancy. The Catan2 adapter owns game-specific legality and scoring.

## 6. Core Data Model

### 6.1 Coordinates and Geometry

```c
typedef struct HexCoord {
    int q;
    int r;
} HexCoord;

typedef struct Vec2 {
    double x;
    double y;
} Vec2;

typedef struct Pose2D {
    double x;
    double y;
    double angle_radians;
} Pose2D;
```

For a pointy-top hex with radius \(s\):

\[
x=\sqrt{3}s\left(q+\frac{r}{2}\right), \qquad
y=\frac{3}{2}sr
\]

The six axial neighbor offsets are:

\[
(1,0),(1,-1),(0,-1),(-1,0),(-1,1),(0,1)
\]

### 6.2 Topological Entities

```c
#define HEX_SIDE_COUNT 6
#define MAX_VERTEX_TILES 3
#define MAX_VERTEX_EDGES 3
#define MAX_EDGE_TILES 2

typedef struct BoardTile {
    int id;
    HexCoord coordinate;
    int neighbor_ids[HEX_SIDE_COUNT];
    int vertex_ids[HEX_SIDE_COUNT];
    int edge_ids[HEX_SIDE_COUNT];
    int terrain_type;
    int number_token;
} BoardTile;

typedef struct BoardVertex {
    int id;
    Vec2 position;
    int tile_ids[MAX_VERTEX_TILES];
    int edge_ids[MAX_VERTEX_EDGES];
} BoardVertex;

typedef struct BoardEdge {
    int id;
    int vertex_ids[2];
    int tile_ids[MAX_EDGE_TILES];
} BoardEdge;
```

Missing neighbors or incidences use a single documented sentinel such as `-1`. Topology is generated once, validated, then treated as immutable during an ordinary Catan2 match.

### 6.3 Physical and Logical Pieces

```c
typedef enum PieceKind {
    PIECE_SETTLEMENT,
    PIECE_CITY,
    PIECE_ROAD,
    PIECE_ROBBER,
    PIECE_TILE,
    PIECE_NUMBER_TOKEN
} PieceKind;

typedef enum AnchorKind {
    ANCHOR_NONE,
    ANCHOR_TILE,
    ANCHOR_VERTEX,
    ANCHOR_EDGE
} AnchorKind;

typedef struct BoardPiece {
    int id;
    int owner;
    PieceKind kind;
    AnchorKind anchor_kind;
    int anchor_id;
    Pose2D logical_pose;
    Pose2D observed_pose;
    double observation_confidence;
    unsigned int flags;
} BoardPiece;
```

Logical pose is authoritative. Observed pose is evidence. Observation must never directly overwrite the logical anchor.

## 7. Tile-to-Tile Interaction Model

### 7.1 Pairwise Interaction

For adjacent tiles \(i\) and \(j\):

\[
I_{ij}=A_{ij}f(\tau_i,\tau_j,P_i,P_j,t)
\]

where \(A_{ij}\) is the adjacency matrix, \(\tau\) is tile type, and \(P_i\) is the piece state associated with tile \(i\).

The first implementation must support:

- adjacency bonuses or penalties;
- blockers affecting one tile or a configurable neighborhood radius;
- resource influence propagating across neighboring tiles;
- regional aggregation;
- interaction enable/disable flags per game adapter.

### 7.2 Optional Continuous Field

The generic engine may evolve a scalar field using:

\[
x_i(t+\Delta t)=x_i(t)+\Delta t\left[s_i-d_ix_i+\sum_j A_{ij}k_{ij}(x_j-x_i)\right]
\]

This supports later hazards, weather, contamination, trade pressure, heat, or other spatial processes. Catan2 does not need to enable every field mode during the first milestone.

### 7.3 Determinism

Every interaction update must define:

- stable tile traversal order;
- stable piece traversal order;
- explicit time step;
- explicit random seed when stochastic behavior is enabled;
- fixed numeric precision policy;
- deterministic conflict resolution.

## 8. Physical Observation and Reconciliation

Physical input is represented independently of its sensor source:

```json
{
  "schema": "leafos.board-observation.v1",
  "observation_id": "camera-000104",
  "recorded_utc": "2026-07-17T00:00:00Z",
  "piece_id": 12,
  "piece_kind": "road",
  "pose": {"x": 4.21, "y": 2.08, "angle_radians": 1.0472},
  "confidence": 0.94,
  "source": "overhead-camera"
}
```

Candidate anchors are ranked using:

\[
a^*=\arg\min_a\left[
\frac{\|p-c_a\|^2}{\sigma_p^2}+
\frac{d_\theta(\theta,\theta_a)^2}{\sigma_\theta^2}+
\lambda C_{\mathrm{illegal}}(a)
\right]
\]

The reconciler returns one of:

- `accepted`: one legal candidate exceeds the confidence threshold;
- `ambiguous`: multiple candidates remain plausible;
- `rejected`: no legal candidate exists;
- `deferred`: more observations are required.

Ambiguous observations must be presented to the TUI. They must not silently mutate authoritative state.

## 9. Catan2 Adapter Requirements

The Catan2 adapter shall:

1. Generate the standard 19-hex radius-two board topology.
2. Produce exactly 54 unique vertices and 72 unique edges for the standard layout.
3. Place settlements and cities on vertices.
4. Place roads on edges.
5. Place the robber on a tile.
6. Derive a building's productive tiles from vertex incidence.
7. Derive road connectivity from edge and vertex incidence.
8. Preserve continual resource increase as the Catan2 benchmark rule.
9. Allow optional tile-neighborhood modifiers without changing the topology core.
10. Preserve deterministic bots and CPU-authoritative brain validation.

Production for a piece at vertex \(v\) is derived from tile-vertex incidence rather than copied tile identifiers:

\[
R_{p,r}=m(p)\sum_t B_{TV}(t,v_p)Y_{t,r}U_t
\]

where \(m(p)\) is the building multiplier, \(Y_{t,r}\) is tile yield for resource \(r\), and \(U_t\) is zero when the tile is blocked.

## 10. Brain Hook Contract

Replace loose integer extraction with strict JSON:

```json
{
  "schema": "leafos.catan2.brain-decision.v1",
  "tile_id": 12,
  "confidence": 0.81,
  "reason_code": "ore-deficit"
}
```

Requirements:

- Local commands only.
- Loopback endpoints only.
- Configurable per-call timeout.
- Bounded stdout and stderr capture.
- No shell interpolation of state paths or model output.
- GPU command proposes.
- CPU command validates or overrides.
- Invalid, late, or malformed decisions fall back to deterministic policy.
- Every proposal, override, timeout, and fallback emits evidence.

On Windows, prefer `CreateProcessW`, explicit arguments, pipes, and `WaitForSingleObject` over `_popen` command strings.

## 11. Event and Checkpoint Contract

The benchmark shall emit one JSON object per stdout line. Human diagnostics go to stderr.

Required event types:

- `session.started`
- `topology.generated`
- `piece.placed`
- `piece.observed`
- `piece.moved`
- `piece.snapped`
- `piece.rejected`
- `state.ambiguous`
- `brain.proposed`
- `brain.overridden`
- `brain.fallback`
- `tile.interaction`
- `tick.completed`
- `checkpoint.written`
- `session.completed`
- `session.interrupted`
- `session.failed`

Example tick event:

```json
{
  "schema": "leafos.catan2.event.v1",
  "sequence": 17,
  "event": "tick.completed",
  "tick": 8,
  "player": 0,
  "gpu_proposal": 12,
  "cpu_selection": 4,
  "resource": "ore",
  "amount": 200,
  "brain": {
    "gpu_valid": true,
    "cpu_override": true,
    "fallback": false,
    "elapsed_ms": 284
  }
}
```

Every event includes a monotonically increasing sequence number. A replay must reject missing, duplicated, or reordered records.

## 12. Full-Screen TUI Integration

The TUI remains a separate controller process. It must not be implemented inside the benchmark executable.

Required spatial panels:

- Board topology and selected entity.
- Current tick and active player.
- Tile resource state and neighborhood effects.
- Piece inventory and anchors.
- GPU proposal and CPU final decision.
- Override, timeout, invalid-response, and fallback counts.
- Observation confidence and unresolved ambiguities.
- Worker, provider, checkpoint, and event-stream health.

Required controls:

- Pause after tick.
- Pause after match.
- Resume.
- Stop after tick.
- Emergency checkpoint and terminate.
- Enable or disable GPU proposals.
- Select deterministic CPU-only mode.
- Resolve an ambiguous physical observation.
- Restart the local provider.
- Open the evidence directory.

The terminal must be restored after normal completion, interruption, worker failure, provider timeout, and configuration rejection.

## 13. Proposed File Layout

```text
board-game-lab/
  include/
    board_geometry.h
    board_topology.h
    board_piece.h
    board_observation.h
    board_interaction.h
  src/
    board_geometry.c
    board_topology.c
    board_piece.c
    board_observation.c
    board_interaction.c
  games/
    catan2/
      catan2_board.c
      catan2_rules.c
      catan2_interactions.c
      catan2_benchmark.c
  tests/
    test_board_geometry.c
    test_board_topology.c
    test_board_piece.c
    test_board_observation.c
    test_board_interaction.c
    test_catan2_replay.c
```

Python/TUI integration:

```text
board_game_lab/
  session_models.py
  session_engine.py
  session_worker.py
  spatial_events.py
  tui.py
```

## 14. Ordered Work Packages

### GLI-01 — Extract Baseline Contracts

- Preserve current deterministic benchmark behavior as a regression fixture.
- Record baseline seeds, tick counts, resource totals, fallbacks, and hashes.
- Define compiler and runtime commands.
- Gate: baseline run is replayable before structural changes begin.

### GLI-02 — Implement Geometry and Topology

- Add axial coordinates and world-coordinate conversion.
- Generate canonical vertices and edges.
- Generate neighbor and incidence tables.
- Add topology validation and stable identifiers.
- Gate: standard board yields 19 tiles, 54 vertices, and 72 edges with no invalid incidence.

### GLI-03 — Implement Physical Piece Model

- Add piece kinds, anchors, poses, footprints, flags, and ownership.
- Add placement, movement, removal, and occupancy validation.
- Migrate settlements and cities from copied tile lists to vertex anchors.
- Gate: illegal overlap and invalid anchor types are rejected deterministically.

### GLI-04 — Implement Tile Interaction Engine

- Add adjacency queries and pairwise interaction callbacks.
- Add blocker radius and neighborhood effects.
- Add optional scalar-field update interface.
- Gate: disabled interactions reproduce the baseline; enabled fixtures produce stable expected results.

### GLI-05 — Implement Observation Reconciliation

- Define provider-neutral observation records.
- Rank candidate anchors by pose, orientation, and legality.
- Add confidence thresholds and ambiguity state.
- Gate: noisy fixtures resolve correctly or remain explicitly ambiguous.

### GLI-06 — Migrate Catan2 Rules

- Move Catan-specific production and legality into an adapter.
- Add roads and robber behavior.
- Preserve continual harvesting and deterministic bots.
- Gate: legacy mode matches baseline hashes; spatial mode passes new fixtures.

### GLI-07 — Harden Brain Hooks

- Replace loose text parsing with strict JSON.
- Add timeouts, bounded capture, safe argument passing, and reason codes.
- Enforce local-only endpoint policy.
- Gate: malformed, late, illegal, and unavailable brains all fall back without blocking the run.

### GLI-08 — Add Structured Events and Replay

- Emit JSONL on stdout and diagnostics on stderr.
- Add sequence validation and terminal events.
- Add atomic spatial checkpoints.
- Add replay tool and final-state hash.
- Gate: replay reconstructs the same authoritative state and hash.

### GLI-09 — Integrate Scheduler and TUI

- Run benchmark in a worker process.
- Connect command and event queues.
- Render spatial, brain, observation, and checkpoint panels.
- Add controlled pause, stop, and failure recovery.
- Gate: terminal restoration and checkpoint integrity pass all exit-path tests.

## 15. Invariants

The following are non-negotiable:

1. Tile identifiers are unique and stable within a board definition.
2. Every edge references exactly two valid vertices.
3. Every vertex, edge, and tile incidence is reciprocal.
4. A piece has at most one authoritative anchor.
5. A settlement or city anchors only to a vertex.
6. A road anchors only to an edge.
7. A robber anchors only to a tile.
8. Observed pose never directly changes authoritative state.
9. CPU validation remains authoritative.
10. Failed inference never prevents deterministic local progress.
11. Equal configuration, seed, input events, and version produce equal final hashes.
12. No remote provider is contacted.

## 16. Required Tests

### Geometry and Topology

- Axial neighbor symmetry.
- World-to-hex round trip within tolerance.
- Standard board entity counts.
- Boundary tile neighbor counts.
- Reciprocal tile/vertex/edge incidence.
- Duplicate coordinate and identifier rejection.

### Pieces and Rules

- Valid settlement, city, road, and robber anchoring.
- Invalid anchor-kind rejection.
- Occupied-anchor rejection.
- City upgrade behavior.
- Road connectivity and disconnection.
- Robber production blocking.
- Derived production matches known fixtures.

### Interaction

- Pairwise interaction symmetry where required.
- Directional interaction where configured.
- Blocker-radius fixtures.
- Stable update order.
- Disabled interaction baseline equivalence.

### Physical Observation

- Exact anchor match.
- Noisy but resolvable pose.
- Orientation-sensitive road match.
- Ambiguous boundary placement.
- Illegal occupied target.
- Low-confidence defer behavior.

### Brain and Runtime

- Valid GPU proposal accepted by CPU.
- CPU override.
- Illegal tile fallback.
- Malformed JSON fallback.
- Timeout fallback.
- Missing executable fallback.
- Paths containing spaces and punctuation.
- Worker exception produces `session.failed`.
- Interrupt produces checkpoint and `session.interrupted`.

### Replay

- Identical final state and hash from event replay.
- Missing sequence detection.
- Duplicate sequence detection.
- Reordered sequence detection.
- Corrupted checkpoint rejection.

## 17. Evidence Requirements

Completion evidence must include:

- Build command and compiler version.
- Unit and integration test report.
- Standard-board topology summary.
- Baseline and spatial-mode benchmark summaries.
- At least one CPU-only run.
- At least one valid dual-brain run when the local provider is available.
- One forced timeout/fallback run.
- One ambiguous physical-observation fixture.
- JSONL event log.
- Final checkpoint.
- Replay report and final-state hash.
- TUI exit-path validation report.

## 18. Completion Gates

This work order is complete only when all gates pass:

1. **Topology gate:** 19 tiles, 54 vertices, and 72 edges are generated and validated.
2. **Authority gate:** no observation or GPU proposal bypasses CPU/rule validation.
3. **Determinism gate:** replay reproduces the final state hash.
4. **Fallback gate:** unavailable or failed brains do not stop deterministic progress.
5. **Physical-state gate:** ambiguous observations remain unresolved until explicitly reconciled.
6. **Scheduler gate:** pause and graceful stop occur at documented safe boundaries.
7. **Checkpoint gate:** completed, interrupted, and failed states are distinct and recoverable.
8. **TUI gate:** the PowerShell terminal is restored on every tested exit path.
9. **Regression gate:** legacy interaction-disabled mode matches recorded baseline behavior.
10. **Evidence gate:** all required artifacts are present and linked from the run report.

## 19. Definition of Done

LeafOS can launch Catan2 from the full-screen terminal interface, generate a validated spatial board, place and move logical pieces, calculate tile and neighborhood interactions, accept simulated physical observations, reconcile observations without bypassing authority, obtain bounded local GPU proposals, validate them on the CPU, checkpoint every safe boundary, and replay the event stream to the same final state.

At that point Catan2 is no longer merely a resource-choice loop. It is the first adapter on a reusable board-spatial reasoning substrate.

## 20. Evidence Log

- 2026-07-18: Added `core/bench/board_spatial.py` with axial coordinates, pointy-top world coordinates, deterministic radius-two hex topology generation, reciprocal incidence validation, and topology summary.
- 2026-07-18: Updated `core/bench/catan2bench.py` so Catan2 uses a 19-tile spatial board, four vertex-anchored settlement/city pieces, 18 productive tiles, and production through building vertex incidence.
- 2026-07-18: Added ordered `leafos.catan2.event.v1` JSONL events for `session.started`, `topology.generated`, `piece.placed`, `harvest.completed`, `tick.completed`, and `session.completed`.
- 2026-07-18: Added `tests/test_board_spatial.py` and updated `tests/catan2bench.sh` to enforce 19 tiles, 54 vertices, 72 edges, spatial mode, vertex production anchors, and event sequencing.
- 2026-07-18: Verification passed: `python -m py_compile ProjectLeaf\leafos_taskpack\core\bench\board_spatial.py ProjectLeaf\leafos_taskpack\core\bench\catan2bench.py ProjectLeaf\leafos_taskpack\tests\test_board_spatial.py`.
- 2026-07-18: Verification passed: `python -m unittest ProjectLeaf\leafos_taskpack\tests\test_board_spatial.py`.
- 2026-07-18: Verification passed: `bash ProjectLeaf/leafos_taskpack/tests/catan2bench.sh`.
- 2026-07-18: Verification passed: `pwsh -NoProfile -File ProjectLeaf\leafos_taskpack\bin\leafctl.ps1 catan2bench --profile 4m --fast --ticks 2 --provider-mode off --no-gpu-probe --quiet --json`.

## 21. Carry Forward

- Implement generic board pieces with anchor kind, owner, logical pose, observed pose, confidence, and occupancy flags.
- Add road edge anchoring, robber tile anchoring, occupied-anchor rejection, and city-upgrade validation.
- Add replay validation for event sequence gaps, duplicates, and reordering.
- Keep Vulkan/LLM proposals advisory; CPU validation remains the authority layer.
