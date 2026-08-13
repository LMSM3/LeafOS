# LeafOS Model Library

```text
Status: Usable → Machine-validated (2026-07-19 closeout)
Branch: ~C
System: LeafOS / Project New Leaf
File: model-library.md
Purpose: Local model registry, routing policy, role contracts, and symbolic model metadata
```

## 1. Purpose

The **LeafOS Model Library** is the registry of the local **stack** that LeafOS
can route through the agentic coding pipeline. In LeafOS documentation, stack
means all models downloaded and locally available to this instance.

It does not treat models as magic agents. That would be embarrassing, and worse, inaccurate. It treats models as **execution resources** with assigned roles, contracts, limits, and parser expectations.

```text
model endpoint → logical lane → output contract → parser → accepted artifact
```

Core doctrine:

```text
Models propose.
Parsers validate.
LeafOS executes.
Tests verify.
Reports remember.
```

## 2. Symbol Layer

```text
𔓘  @leaf.root        Root system / model library origin
🍃  @leaf.active      Active model runtime
❦   @leaf.work        Work order or task route
⋆   @leaf.model       Model-generated action
𓆝  @leaf.lane        Logical lane / helper routing
⿻   @leaf.overlay     Context merge / routing overlay
𓂃  @leaf.flow        Execution or model request flow
⚠︎  @leaf.alert       Warning or error state
⚝   @leaf.verify      Verified accepted result
ꕤ   @leaf.checkpoint  Stable model profile checkpoint
⎙   @leaf.print       Report/export/model card output
⬪   @leaf.event       Model event packet
```
## Add more event icons  !

## 3. Model Library Tree

```text
models/
│
├── model-library.md
│   └── human-readable registry
│
├── model-library.json
│   └── machine-readable registry
│
├── profiles/
│   ├── brain-14b.json
│   ├── coder-12b-fable.json
│   ├── coder-9b-fast.json
│   ├── reviewer-9b.json
│   └── fallback-small.json
│
├── prompts/
│   ├── brain.system.txt
│   ├── coder.system.txt
│   ├── reviewer.system.txt
│   └── reporter.system.txt
│
├── routing/
│   ├── lanes.json
│   ├── endpoints.json
│   ├── contracts.json
│   └── gpu-bindings.json
│
├── eval/
│   ├── brain-taskpack-eval.jsonl
│   ├── coder-diff-eval.jsonl
│   ├── reviewer-json-eval.jsonl
│   └── refusal-safety-eval.jsonl
│
└── reports/
    ├── model-benchmark-log.tsv
    ├── model-failure-log.tsv
    └── model-selection-report.md
```

## 4. Core Roles

LeafOS uses roles, not fake personalities.

```text
brain     → planning, task decomposition, graph generation
coder     → bounded unified-diff generation
reviewer  → patch scope/risk/test/doc review
reporter  → summaries, reports, user-facing explanation
fallback  → small helper, classification, repair hints
```

## 5. Role Contracts

### 5.1 Brain Contract

The Brain model outputs structured taskpacks or graphs.

Accepted output:

```text
JSON only
```

Primary artifacts:

```text
taskpack.json
agent.graph.json
repair_plan.json
completion_gate.json
```

Rejected output:

```text
prose-only plan
missing completion gate
missing files_to_edit
dangerous commands
unsupported node types
absolute path writes
```

Symbol path:

```text
𔓘 root → 🍃 active → ⋆ Brain → ⿻ parser → ❦ graph
```

### 5.2 Coder Contract

The Coder model outputs patches.

Accepted output:

```text
unified diff only
```

Primary artifacts:

```text
extracted.patch
patch_scope.json
changed_lines.diff
```

Rejected output:

```text
prose-only answer
markdown explanation without patch
invented file paths
edits outside allowed file list
patch fails git apply --check
claims verification
```

Symbol path:

```text
❦ node → ⋆ Coder → ⿻ diff parser → 𓂃 patch apply → ⚝ verify
```

### 5.3 Reviewer Contract

The Reviewer model outputs structured review JSON.

Accepted output:

```text
review_result.json
```

Reviewer cannot directly edit files.

Reviewer may classify:

```text
scope risk
test risk
documentation risk
security risk
parser contract risk
```

Reviewer output shape:

```json
{
  "leafos_object": "review_result",
  "version": "0.7.0",
  "symbol": "𓆝",
  "review_type": "scope",
  "status": "pass",
  "risk_level": "low",
  "blocking": false,
  "findings": [],
  "recommended_actions": []
}
```

Symbol path:

```text
⋆ patch → 𓆝 reviewer → ⿻ review parser → ⚠︎ warn or ⚝ approve
```

### 5.4 Reporter Contract

The Reporter model creates user-facing summaries from already verified data.

Accepted output:

```text
report.md
report.json
```

Reporter cannot invent pass/fail status. It must read verification artifacts.

Symbol path:

```text
⚝ verified artifacts → ⎙ report
```

## 6. Current Candidate Models

### 6.1 Primary Coder / Fable Lane

```text
Name:
  yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF

Role:
  primary coder

Lane:
  slot.coder.patch

Best use:
  bounded patch generation
  code synthesis
  project scaffolding
  test generation
  refactor of known files

Contract:
  unified_diff

Symbol:
  ⋆ Coder / Fable
```

Notes:

```text
Use for careful implementation where patch quality matters more than speed.
Do not let it rewrite broad repository sections unless the Brain explicitly scopes the action.
```

### 6.2 Secondary Coder / Fast Helper

```text
Name:
  Jackrong/Qwopus3.5-9B-Coder-MTP-GGUF

Role:
  secondary coder / fast helper

Lane:
  slot.coder.fast
  slot.repair.quick
  slot.docs.quick

Best use:
  small edits
  quick test generation
  syntax fixes
  repair hints
  alternate patch attempt

Contract:
  unified_diff or review_json, depending on route

Symbol:
  𓆝 helper lane
```

Notes:

```text
Use for cheaper fast attempts before escalating to the larger coder.
Good for quick repairs and local file transforms.
```

### 6.3 Brain Candidate / Opus-Like Planner

```text
Name:
  yuxinlu1/gemma-4-12B-it-Claude-4.6-4.8-Opus-GGUF

Role:
  brain / planner

Lane:
  slot.brain.plan
  slot.brain.repair
  slot.brain.gate_design

Best use:
  work-order decomposition
  project graph generation
  repair planning
  completion gate design
  template selection

Contract:
  json_taskpack
  agent_graph_json

Symbol:
  ⋆ Brain
```

Notes:

```text
Use as architecture and planning layer.
Must output JSON taskpacks, not poetic tactical fog.
```

### 6.4 Brain Candidate / Reasoning Planner

```text
Name:
  tvall43/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap-gguf

Role:
  reasoning brain / planner

Lane:
  slot.brain.deep
  slot.review.architecture

Best use:
  deeper decomposition
  failure analysis
  test strategy
  multi-step repair planning
  codebase-level reasoning

Contract:
  json_taskpack
  review_json

Symbol:
  ⋆ Brain / 𓆝 reviewer
```

Notes:

```text
Use when task planning needs more structured reasoning.
Do not use for direct broad code mutation unless routed through the Coder contract.
```

## 7. Suggested Model Routing Policy

```text
Simple task:
  brain-small or mock route
  coder-fast
  shell verify

Medium task:
  brain-14b
  coder-12b-fable
  reviewer optional

Hard task:
  brain-14b deep
  coder-12b-fable
  reviewer-9b or brain-review
  repair loop enabled

Documentation task:
  brain for outline
  coder or reporter for docs
  reviewer for README gate

Repair task:
  brain.repair
  coder.fast first
  coder.fable if fast repair fails
```

## 8. Lane Map

```json
{
  "leafos_object": "model_lane_map",
  "version": "0.7.0",
  "lanes": [
    {
      "lane": "slot.brain.plan",
      "symbol": "⋆",
      "role": "brain",
      "contract": "json_taskpack",
      "default_model_profile": "brain-14b"
    },
    {
      "lane": "slot.coder.patch",
      "symbol": "⋆",
      "role": "coder",
      "contract": "unified_diff",
      "default_model_profile": "coder-12b-fable"
    },
    {
      "lane": "slot.coder.fast",
      "symbol": "𓆝",
      "role": "coder",
      "contract": "unified_diff",
      "default_model_profile": "coder-9b-fast"
    },
    {
      "lane": "slot.review.scope",
      "symbol": "𓆝",
      "role": "reviewer",
      "contract": "review_json",
      "default_model_profile": "reviewer-9b"
    },
    {
      "lane": "slot.report.summary",
      "symbol": "⎙",
      "role": "reporter",
      "contract": "report_markdown",
      "default_model_profile": "reporter-default"
    }
  ]
}
```

## 9. Endpoint Profiles

Example endpoint layout:

```json
{
  "leafos_object": "model_endpoints",
  "version": "0.7.0",
  "endpoints": [
    {
      "id": "brain.local",
      "url": "http://127.0.0.1:8081/v1/chat/completions",
      "model": "local-brain-14b",
      "gpu_binding": "CUDA_VISIBLE_DEVICES=0",
      "logical_only": false
    },
    {
      "id": "coder.local",
      "url": "http://127.0.0.1:8082/v1/chat/completions",
      "model": "local-coder-12b",
      "gpu_binding": "CUDA_VISIBLE_DEVICES=1",
      "logical_only": false
    },
    {
      "id": "reviewer.logical",
      "url": "http://127.0.0.1:8082/v1/chat/completions",
      "model": "local-coder-12b",
      "gpu_binding": "CUDA_VISIBLE_DEVICES=1",
      "logical_only": true
    }
  ]
}
```

Important:

```text
logical_only = true means scheduler label, not separate hardware.
```

Same brutal reality as GPU slots: names do not create hardware. If they did, everyone would name their laptop “datacenter” and call it a day.

## 10. Model Card Template

Each model should have a model card.

```markdown
# Model Card — MODEL_NAME

```text
Profile ID:
Role:
Lane:
Contract:
Endpoint:
GPU binding:
Context target:
Temperature:
Max tokens:
Status:
```

## Purpose

## Strengths

## Weaknesses

## Accepted Contracts

## Rejected Output Patterns

## Recommended Prompt Header

## Verification Requirements

## Known Failure Modes

## Benchmark Notes

## Checkpoint Status
```

## 11. Contract Registry

```json
{
  "leafos_object": "contract_registry",
  "version": "0.7.0",
  "contracts": [
    {
      "id": "json_taskpack",
      "parser": "core/parser/parse_brain_taskpack.py",
      "required_keys": [
        "leafos_object",
        "version",
        "title",
        "summary",
        "files_to_inspect",
        "files_to_edit",
        "nodes",
        "completion_gate"
      ]
    },
    {
      "id": "unified_diff",
      "parser": "core/parser/parse_coder_patch.sh",
      "validators": [
        "git apply --check",
        "validate_patch_scope.sh"
      ]
    },
    {
      "id": "review_json",
      "parser": "core/parser/parse_review_result.py",
      "required_keys": [
        "leafos_object",
        "version",
        "review_type",
        "status",
        "risk_level",
        "blocking",
        "findings"
      ]
    },
    {
      "id": "report_markdown",
      "parser": "core/parser/parse_report.sh",
      "validators": [
        "required_sections_present"
      ]
    }
  ]
}
```

## 12. Model Selection Ladder

```text
Need architecture?
  use Brain

Need code?
  use Coder

Need small repair?
  use Fast Coder

Need risk check?
  use Reviewer

Need summary?
  use Reporter

Need raw shell truth?
  use no model, run the command
```

Last line is important. The best model for `bash -n` is not a model. It is `bash -n`. Terrible news for the cult of autocomplete, excellent news for reality.

## 13. Recommended Prompt Headers

### 13.1 Brain Header

```text
𔓘 You are the LeafOS Brain model.
Your output contract is JSON only.
Create bounded taskpacks or agent graphs.
Do not write code directly.
Do not claim verification.
Include completion gates.
```

### 13.2 Coder Header

```text
⋆ You are the LeafOS Coder model.
Your output contract is unified diff only.
Only edit allowed files.
Do not include prose.
Do not claim tests passed.
If no safe patch is possible, output LEAFOS_NO_PATCH: reason.
```

### 13.3 Reviewer Header

```text
𓆝 You are the LeafOS Reviewer model.
Your output contract is review JSON only.
Review patch scope, risk, tests, and docs.
Do not rewrite files.
Do not block unless policy says findings are blocking.
```

### 13.4 Reporter Header

```text
⎙ You are the LeafOS Reporter model.
Summarize verified artifacts only.
Do not invent pass/fail status.
Mention warnings and incomplete gates clearly.
```

## 14. Eval Tasks

### 14.1 Brain Eval

Input:

```text
Create a tiny C CLI calculator with tests and README.
```

Expected:

```text
valid taskpack JSON
files_to_edit populated
completion_gate present
test commands safe
```

### 14.2 Coder Eval

Input:

```text
Patch README.md to add a Usage section.
Allowed files: README.md
```

Expected:

```text
unified diff only
touches README.md only
git apply --check passes
```

### 14.3 Reviewer Eval

Input:

```text
Review this patch for scope violations.
Allowed files: README.md
Patch touches README.md and src/main.c.
```

Expected:

```text
review_json
risk_level high or medium
blocking true or policy_warning
finding mentions src/main.c outside scope
```

## 15. Failure Log Taxonomy

```text
parse_failure
schema_failure
scope_failure
patch_apply_failure
empty_patch
prose_only
invented_file
unsafe_command
missing_completion_gate
verification_claim_without_evidence
timeout
model_endpoint_down
context_overflow
```

Each failure should become:

```json
{
  "event": "model_failure",
  "symbol": "⚠︎",
  "model_profile": "coder-12b-fable",
  "lane": "slot.coder.patch",
  "failure_type": "prose_only",
  "artifact": "runs/latest/coder/content.txt",
  "repair_allowed": true
}
```

## 16. Training Export Hooks

For 0.8.0, each model event should be exportable as:

```text
Unicode symbolic form
ASCII alias form
natural-language instruction form
machine-action form
```

Example:

```json
{
  "unicode": "🍃 ❦ WO-006 ⋆ coder 𓂃 patch ⚝ verify",
  "ascii": "@leaf.active @leaf.work WO-006 @leaf.model coder @leaf.flow patch @leaf.verify",
  "natural": "In active LeafOS runtime, select WO-006, ask the coder to generate a patch, apply it, and verify it.",
  "machine_action": {
    "runtime": "active",
    "work_order": "WO-006",
    "actor": "coder",
    "action": "generate_patch",
    "verification_required": true
  }
}
```

## 17. Stable Model Profile Criteria

A model profile can be marked stable when:

```text
passes brain/coder/reviewer evals for its role
produces correct contract format at least 8/10 times
does not invent files in basic tests
does not claim verification without evidence
handles LEAFOS_NO_PATCH correctly
works within target context window
does not require fragile prompt hacks
```

Checkpoint line:

```text
ꕤ model profile stable
```

## 18. Open Questions

```text
Should reviewer be a separate physical model or a logical lane on the coder endpoint?
Should 9B be used for fast repair before or after reviewer?
Should Brain generate tests, or should Coder generate tests from Brain gates?
Should symbolic training export include rejected raw model outputs?
How much context should be stored in model event envelopes?
```

## 19. Final Doctrine

```text
A model is not trusted because it is large.
A model is trusted only inside a narrow contract.
A lane is not trusted because it has a name.
A lane is trusted only after its parser accepts the artifact.
A patch is not accepted because it looks plausible.
A patch is accepted only after git and tests stop complaining.
```

Tiny little governance miracle. Ugly, strict, and vastly better than letting a 12B model freestyle inside your repo like a caffeinated raccoon with commit access.

---

# 20. Real Model Assignments — v0.7.0 / v0.8.0 Draft

```text
Status: Active assignment block
Branch: ~C
Purpose: Bind real Hugging Face model targets to LeafOS Brain, Coder, Helper, and Reviewer lanes
```

## 20.1 Assignment Doctrine

LeafOS does not assign models by vibes, naming mythology, or whatever benchmark screenshot wandered across the internet this morning.

A model assignment must specify:

```text
role
lane
endpoint
contract
quant
fallback
parser
verification burden
```

The operating rule remains:

```text
model → lane → contract → parser → accepted artifact
```

No model gets direct file authority. No model gets to claim verification. No model gets to touch the repo without surviving the parser border checkpoint like everyone else. Grim, but civilized.

---

## 20.2 Primary Brain Assignment

LeafOS supports two primary Brain candidates.

### Primary Brain A — High-Capacity / Opus-Sonnet Distilled

```text
Profile ID:
  brain-primary-27b-nvfp4-mtp

Model:
  Brian6145/Qwen3.6-27B-Claude-Opus-Sonnet-Distilled-NVFP4-MTP

Role:
  primary Brain / deep planner

Lane:
  slot.brain.plan
  slot.brain.deep
  slot.brain.repair
  slot.brain.gate_design

Contract:
  json_taskpack
  agent_graph_json
  repair_plan_json
  completion_gate_json

Best use:
  complex work-order decomposition
  multi-node project graph generation
  difficult repair planning
  architecture review
  README/test/doc gate design
  template selection

Do not use for:
  direct file mutation
  direct patch generation
  unparsed shell command generation
  claims of test success

Preferred runtime:
  vLLM or SGLang-compatible local API if the hardware stack supports NVFP4/MTP efficiently

LeafOS symbol:
  ⋆ Brain-Primary-27B
```

#### Brain A prompt header

```text
𔓘 You are the LeafOS Primary Brain.
Your output contract is strict JSON only.
Create bounded taskpacks, agent graphs, repair plans, and completion gates.
Do not write code directly.
Do not claim verification.
All nodes must include parser-compatible output contracts.
```

#### Brain A risk note

```text
Use this as the highest-quality planner only if the local deployment stack can actually serve it cleanly.
If it is unstable, slow, unavailable, or awkward under the current GPU layout, demote it to experimental.
```

---

### Primary Brain B — Conservative Local Brain / GGUF Reasoning Planner

```text
Profile ID:
  brain-primary-14b-gguf

Model:
  tvall43/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap-gguf

Role:
  primary Brain fallback / conservative planner

Lane:
  slot.brain.plan
  slot.brain.repair
  slot.review.architecture

Contract:
  json_taskpack
  agent_graph_json
  review_json

Best use:
  project graph generation
  medium-to-hard task decomposition
  repair planning
  test strategy
  architecture review
  fallback primary Brain if 27B is impractical

Do not use for:
  broad direct patching
  unstructured prose planning
  direct shell command execution

Preferred runtime:
  llama.cpp or compatible local GGUF runner

LeafOS symbol:
  ⋆ Brain-Primary-14B
```

#### Brain B prompt header

```text
𔓘 You are the LeafOS Conservative Brain.
Your output contract is JSON only.
Prefer small graph nodes and explicit gates.
Do not produce code unless routed through a coder lane.
```

---

## 20.3 Brain Selection Policy

```text
If task is simple:
  use mock route or brain-primary-14b

If task is medium:
  use brain-primary-14b

If task is hard architecture:
  try brain-primary-27b-nvfp4-mtp if runtime is stable
  otherwise use brain-primary-14b

If task is repair:
  use brain-primary-14b first
  escalate to brain-primary-27b only if repeated failure occurs

If model output violates JSON contract:
  reject
  retry once with stricter header
  then demote model for that run
```

Decision table:

```text
Task Type                 Preferred Brain              Fallback
---------------------------------------------------------------------------
small CLI task             brain-primary-14b            mock route
template selection          brain-primary-14b            brain-primary-27b
multi-file architecture     brain-primary-27b            brain-primary-14b
repair after failed patch   brain-primary-14b            brain-primary-27b
review architecture         brain-primary-14b            reviewer lane
```

---

# 21. Real Coding Assignments

## 21.1 Primary Coder — Fable 12B

```text
Profile ID:
  coder-primary-12b-fable

Model:
  yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF

Role:
  primary coder

Lane:
  slot.coder.patch
  slot.coder.testgen
  slot.coder.docs
  slot.coder.refactor

Contract:
  unified_diff

Best use:
  bounded patch generation
  test generation
  README/doc patching
  source file creation
  local refactor inside allowed file list
  repair patches after parser/test failure

Do not use for:
  whole-repo rewrites unless explicitly scoped
  claims of verification
  prose-only “I fixed it” output
  editing files outside allowed_files

Preferred runtime:
  llama.cpp / LM Studio / Jan / Ollama-compatible GGUF runtime

LeafOS symbol:
  ⋆ Coder-Fable
```

### Coder prompt header

```text
⋆ You are the LeafOS Primary Coder.
Your output contract is unified diff only.
Only edit files listed in allowed_files.
Do not include prose.
Do not claim tests passed.
If no safe patch is possible, output:
LEAFOS_NO_PATCH: reason
```

---

## 21.2 Multiple Coder Instances

LeafOS may run one or more instances of the same coder model.

```text
Instance A:
  lane: slot.coder.patch
  purpose: main implementation
  quant: Q4_K_M or Q6_K

Instance B:
  lane: slot.coder.testgen
  purpose: tests and smoke checks
  quant: Q3_K_M or Q4_K_M

Instance C:
  lane: slot.coder.docs
  purpose: README and docs
  quant: Q3_K_M or Q4_K_M

Instance D:
  lane: slot.coder.repair
  purpose: fast repair attempt
  quant: Q2_K or Q3_K_M
```

Important:

```text
Multiple instances do not mean multiple independent minds.
They are scheduler lanes pointing at one or more local model servers.
```

Same rule as GPU slot labels. Naming a lane does not create extra hardware. Humanity keeps trying this trick. Physics remains unimpressed.

---

## 21.3 Helper Assignments

Helpers may use the same Fable 12B model at cheaper quants or separate future models.

```text
Profile ID:
  helper-coder-fable-lowquant

Model:
  yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF

Role:
  helper / repair / docs / testgen

Lane:
  slot.helper.patchlet
  slot.helper.docs
  slot.helper.testgen
  slot.helper.error_summary

Contract:
  unified_diff
  review_json
  report_markdown

Best use:
  tiny file edits
  syntax repair
  README section patches
  test smoke-script creation
  failure summarization
  parser error explanation

Preferred quant:
  Q2_K for tiny helpers
  Q3_K_M for fast useful helpers
  Q4_K_M for reliable helper patches
```

Additional helper model candidates may be added under:

```text
models/profiles/helper-extra-*.json
```

Placeholder:

```text
helper-extra-01:
  role: TBD
  lane: slot.helper.misc
  contract: review_json or report_markdown
  status: unassigned
```

---

# 22. Quantization Assignment Policy

## 22.1 Fable 12B Quant Table

Current Fable 12B GGUF assignment table:

```text
Quant     Size       LeafOS Use
---------------------------------------------------------------
Q2_K      4.83 GB    emergency / tiny helper / low-memory repair
Q3_K_M    6.09 GB    fast helper / testgen / docs / secondary coder
Q4_K_M    7.38 GB    default coder / recommended practical baseline
Q6_K      9.79 GB    high-quality coder / careful patches
Q8_0      12.7 GB    near-full-quality coder when memory allows
```

Earlier model-card estimates may show slightly smaller rounded sizes:

```text
Q2_K      ~4.5 GB
Q3_K_M    ~5.7 GB
Q4_K_M    ~6.87 GB
Q6_K      ~9.11 GB
Q8_0      ~11.8 GB
```

LeafOS should store both:

```text
reported_size_hf_ui
reported_size_model_card
```

because websites, file views, and rounded model-card tables love disagreeing just enough to make automation annoying. Naturally.

## 22.2 Quant Selection Rules

```text
Q2_K:
  Use only for emergency low-memory helper routes.
  Accept lower quality.
  Good for classification, tiny repairs, and rough summaries.

Q3_K_M:
  Use for helper lanes and fast secondary coder attempts.
  Better quality than Q2_K while still small enough for tight VRAM.

Q4_K_M:
  Default coder quant.
  Use for primary coding unless there is a reason not to.
  Best balance of quality, speed, and memory.

Q6_K:
  Use for careful coding, difficult patches, or repeated repair failures.
  Good when 12 GB class VRAM has enough context headroom.

Q8_0:
  Use only when memory allows and quality matters more than speed/context.
  On 12 GB GPUs, this may be tight or impractical depending on context and KV cache.
```

## 22.3 Artifact Warning

If a repository file list shows tiny entries such as:

```text
Q8_0   465 MB
BF16   862 MB
F16    862 MB
```

treat those as suspicious for full-model assignment until verified.

Possible meanings:

```text
split shard
adapter
metadata-related artifact
partial file
non-main artifact
```

LeafOS should not assign those as primary model files unless the loader confirms they are valid runnable model targets.

Rule:

```text
If llama.cpp, LM Studio, or the selected runtime cannot load it, it is not a model profile.
It is just a file with ambition.
```

---

# 23. Real Endpoint Assignment

## 23.1 Two-Endpoint Baseline

```json
{
  "leafos_object": "real_endpoint_assignment",
  "version": "0.7.0",
  "mode": "two_endpoint_baseline",
  "endpoints": [
    {
      "id": "brain.local",
      "url": "http://127.0.0.1:8081/v1/chat/completions",
      "role": "brain",
      "preferred_model_profile": "brain-primary-14b-gguf",
      "experimental_model_profile": "brain-primary-27b-nvfp4-mtp",
      "contract": "json_taskpack",
      "symbol": "⋆",
      "status": "primary"
    },
    {
      "id": "coder.local",
      "url": "http://127.0.0.1:8082/v1/chat/completions",
      "role": "coder",
      "preferred_model_profile": "coder-primary-12b-fable",
      "preferred_quant": "Q4_K_M",
      "quality_quant": "Q6_K",
      "low_memory_quant": "Q3_K_M",
      "contract": "unified_diff",
      "symbol": "⋆",
      "status": "primary"
    }
  ]
}
```

## 23.2 Three-Endpoint 0.7.0 Lane Split

```json
{
  "leafos_object": "real_endpoint_assignment",
  "version": "0.7.0",
  "mode": "brain_coder_reviewer",
  "endpoints": [
    {
      "id": "brain.local",
      "port": 8081,
      "role": "brain",
      "profile": "brain-primary-14b-gguf",
      "contract": "json_taskpack"
    },
    {
      "id": "coder.local",
      "port": 8082,
      "role": "coder",
      "profile": "coder-primary-12b-fable",
      "quant": "Q4_K_M",
      "contract": "unified_diff"
    },
    {
      "id": "reviewer.logical",
      "port": 8082,
      "role": "reviewer",
      "profile": "coder-primary-12b-fable",
      "quant": "Q3_K_M or Q4_K_M",
      "contract": "review_json",
      "logical_only": true
    }
  ]
}
```

## 23.3 Multi-Instance Coder Layout

```text
coder.local.main
  port: 8082
  model: yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF
  quant: Q4_K_M
  lane: slot.coder.patch

coder.local.docs
  port: 8083
  model: yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF
  quant: Q3_K_M
  lane: slot.coder.docs

coder.local.repair
  port: 8084
  model: yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF
  quant: Q3_K_M or Q2_K
  lane: slot.coder.repair
```

This only makes sense if the hardware can actually run those servers simultaneously. Otherwise it is just a JSON-based fantasy novel.

---

# 24. Real Routing Ladder

```text
Default stable route:
  Brain:
    tvall43/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap-gguf
  Coder:
    yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q4_K_M
  Helper:
    yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q3_K_M

High-quality route:
  Brain:
    Brian6145/Qwen3.6-27B-Claude-Opus-Sonnet-Distilled-NVFP4-MTP
  Coder:
    yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q6_K
  Reviewer:
    tvall43/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap-gguf

Low-memory route:
  Brain:
    tvall43/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap-gguf if available
  Coder:
    yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q3_K_M
  Helper:
    yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q2_K

Repair route:
  Brain:
    tvall43/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap-gguf
  Fast repair:
    yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q3_K_M
  Careful repair:
    yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF:Q6_K
```

---

# 25. Real Model Profiles

## 25.1 brain-primary-27b-nvfp4-mtp.json

```json
{
  "profile_id": "brain-primary-27b-nvfp4-mtp",
  "model_repo": "Brian6145/Qwen3.6-27B-Claude-Opus-Sonnet-Distilled-NVFP4-MTP",
  "role": "brain",
  "lanes": [
    "slot.brain.plan",
    "slot.brain.deep",
    "slot.brain.repair",
    "slot.brain.gate_design"
  ],
  "contracts": [
    "json_taskpack",
    "agent_graph_json",
    "repair_plan_json"
  ],
  "runtime": [
    "vLLM",
    "SGLang"
  ],
  "status": "experimental_primary",
  "notes": [
    "Use when NVFP4/MTP deployment is stable.",
    "Do not use for direct patches.",
    "Parser must reject prose-only planning."
  ]
}
```

## 25.2 brain-primary-14b-gguf.json

```json
{
  "profile_id": "brain-primary-14b-gguf",
  "model_repo": "tvall43/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap-gguf",
  "role": "brain",
  "lanes": [
    "slot.brain.plan",
    "slot.brain.repair",
    "slot.review.architecture"
  ],
  "contracts": [
    "json_taskpack",
    "agent_graph_json",
    "review_json"
  ],
  "runtime": [
    "llama.cpp",
    "LM Studio",
    "compatible GGUF runner"
  ],
  "status": "stable_primary_candidate",
  "notes": [
    "Use as default conservative planner.",
    "Good fallback if 27B NVFP4 stack is not practical.",
    "Do not route direct file mutation through this profile."
  ]
}
```

## 25.3 coder-primary-12b-fable.json

```json
{
  "profile_id": "coder-primary-12b-fable",
  "model_repo": "yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF",
  "role": "coder",
  "lanes": [
    "slot.coder.patch",
    "slot.coder.testgen",
    "slot.coder.docs",
    "slot.coder.refactor"
  ],
  "contracts": [
    "unified_diff"
  ],
  "runtime": [
    "llama.cpp",
    "LM Studio",
    "Jan",
    "Ollama"
  ],
  "recommended_quant": "Q4_K_M",
  "quality_quant": "Q6_K",
  "low_memory_quant": "Q3_K_M",
  "emergency_quant": "Q2_K",
  "status": "stable_primary_coder_candidate",
  "notes": [
    "Use Q4_K_M as default patch generator.",
    "Use Q6_K for careful patches.",
    "Use Q3_K_M for helper/docs/testgen lanes.",
    "Reject prose-only output."
  ]
}
```

## 25.4 helper-coder-fable-lowquant.json

```json
{
  "profile_id": "helper-coder-fable-lowquant",
  "model_repo": "yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF",
  "role": "helper",
  "lanes": [
    "slot.helper.docs",
    "slot.helper.testgen",
    "slot.helper.repair",
    "slot.helper.error_summary"
  ],
  "contracts": [
    "unified_diff",
    "review_json",
    "report_markdown"
  ],
  "runtime": [
    "llama.cpp",
    "LM Studio",
    "Ollama"
  ],
  "recommended_quant": "Q3_K_M",
  "emergency_quant": "Q2_K",
  "status": "helper_candidate",
  "notes": [
    "Use for cheap helper actions.",
    "Do not let helper lanes apply patches directly.",
    "All helper output still goes through parsers."
  ]
}
```

---

# 26. Updated Stable Assignment Summary

```text
Primary Brain:
  default stable candidate:
    tvall43/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap-gguf

  high-quality experimental primary:
    Brian6145/Qwen3.6-27B-Claude-Opus-Sonnet-Distilled-NVFP4-MTP

Primary Coder:
  yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF
  default quant: Q4_K_M
  careful quant: Q6_K
  helper quant: Q3_K_M
  emergency quant: Q2_K

Helpers:
  yuxinlu1/gemma-4-12B-coder-fable5-composer2.5-v1-GGUF at Q3_K_M or Q2_K
  additional helpers TBD after evals

Reviewer:
  default logical reviewer:
    same Fable coder model at Q3_K_M/Q4_K_M, review_json contract

  architecture reviewer:
    tvall43/Qwen3.5-14B-A3B-Claude-4.6-Opus-Reasoning-Distilled-reap-gguf
```

Final rule:

```text
The real assignment is not the model name.
The real assignment is the tuple:
(model, quant, lane, endpoint, contract, parser, gate)
```

Miss one part and the whole thing becomes model soup. Nutritious? No. Warm? Maybe. Useful? Barely.

## 27. 2026-07-19 Implementation Closeout

The four profiles in section 25 now exist under `config/model-profiles/` and
are validated by `core/runtime/model_profiles.py`. `leafctl model-profile`
lists, shows, validates, and resolves lanes deterministically on Bash and
PowerShell. Unknown lanes and malformed profiles fail closed. Completion
evidence is recorded in `reports/work-orders/WO-005-G-COMPLETION-REPORT.md`.
