# WO-004-C-02 — Wakeup Integration, Tests, and Export Gate

```text
Status: Implemented and verified (2026-07-19 closeout)
Branch: ~C
System: LeafOS / Project New Leaf
Depends on: WO-004-C-02 / D 
Module: Wakeup integration and completion gate
Primary files: tests/, docs/, completion_map.json, export bundle
```

## 1. Purpose

Integrate the WO-004-C wakeup node into the LeafOS work-order ecosystem.

This second work order compresses the implementation into a testable, exportable, and reportable LeafOS mini-module.

The target flow:

```text
agent-task
  → wakeup node
  → branch test
  → log verification
  → completion map
  → export
  → report
  → checkpoint
```

## 2. Scope

This work order covers:

```text
test creation
README/doc verification
completion map generation
export inclusion rules
LeafOS symbolic training extraction
basic agent graph node packaging
```

It does not change the core wakeup branch behavior from WO-004-C-01.

## 3. Integration Tree

Expected module tree:

```text
WO-004-C/
│
├── wakeup.py
│   └── Python wakeup runtime
│
├── wakeup.sh
│   └── Bash wrapper and run-folder creator
│
├── tickers.txt
│   └── optional ticker universe
│
├── README.md
│   └── user-facing instructions
│
├── tests/
│   ├── test_wakeup_shell.sh
│   │   └── bash and CLI smoke checks
│   │
│   └── test_wakeup_json.py
│       └── structured output validation
│
├── docs/
│   └── wakeup_node.md
│       └── LeafOS node explanation
│
├── runs/
│   └── latest/
│       ├── wakeup_result.json
│       └── wakeup_log.csv
│
├── completion_map.json
│   └── file-by-file completion status
│
├── completion_tree.txt
│   └── annotated completion traversal
│
└── exports/
    └── WO-004-C_wakeup_TIMESTAMP.zip
```

## 4. Agent Graph Representation

The wakeup node should be representable as a LeafOS agent graph node. Side topic TK helper to actually graph graph node connections. 

Example:

```json
{
  "leafos_object": "agent_node",
  "version": "0.4.0-C",
  "id": "WO-004-C-wakeup",
  "symbol": "❦",
  "type": "embedded_action",
  "action": "run_wakeup",
  "entrypoint": "./wakeup.sh",
  "expected_outputs": [
    "runs/latest/wakeup_result.json",
    "runs/wakeup_log.csv"
  ],
  "test_commands": [
    "bash -n wakeup.sh",
    "python3 -m py_compile wakeup.py",
    "./wakeup.sh --force tails",
    "./wakeup.sh --force heads --ticker NVDA"
  ],
  "completion_gate": {
    "required_files": [
      "wakeup.py",
      "wakeup.sh",
      "tickers.txt",
      "README.md"
    ],
    "required_outputs": [
      "runs/latest/wakeup_result.json"
    ]
  }
}
```

## 5. Tests

### 5.1 Shell Smoke Test

Required file:

```text
tests/test_wakeup_shell.sh
```

Recommended checks:

```bash
bash -n wakeup.sh
python3 -m py_compile wakeup.py
./wakeup.sh --force tails
./wakeup.sh --force heads --ticker NVDA
test -f runs/latest/wakeup_result.json
```

Expected result:

```text
exit code 0
JSON result exists
CSV log exists
```

### 5.2 JSON Structure Test

Required file:

```text
tests/test_wakeup_json.py
```

Validate:

```text
leafos_object == leafos_wakeup_result
version exists
branch is heads or tails
context.local_date exists
context.local_time exists
message exists
heads branch has importstring
tails branch has importstring = null
```

Recommended command:

```bash
python3 tests/test_wakeup_json.py runs/latest/wakeup_result.json
```

## 6. README Gate

README must contain:

```text
Purpose
Run
Test branches
Optional stock quote module
Output
Safety note
```

Minimum accepted examples:

```bash
./wakeup.sh
./wakeup.sh --force tails
./wakeup.sh --force heads --ticker NVDA
```

The README must mention that stock quote collection is optional and best-effort.

## 7. Documentation Gate

Required document:

```text
docs/wakeup_node.md
```

Must explain:

```text
WO-004-C purpose
heads/tails branch logic
JSON importstring payload
log files
how this fits LeafOS embedded actions
how to test offline
```

This document is mostly for the future Brain/Coder/Reviewer parser layer. Yes, we are writing docs for the parser. The parser does not appreciate it, because parsers have no soul, which is one of their better qualities.

## 8. Completion Worm Pass

The completion worm shall walk the module and generate:

```text
completion_map.json
completion_tree.txt
```

### 8.1 completion_map.json

Required fields:

```json
{
  "leafos_object": "completion_map",
  "version": "0.4.0-C",
  "work_order": "WO-004-C",
  "status": "verified",
  "required_files": [],
  "required_tests": [],
  "logs": [],
  "export": {}
}
```

Required file entries:

```text
wakeup.py
wakeup.sh
tickers.txt
README.md
tests/test_wakeup_shell.sh
tests/test_wakeup_json.py
docs/wakeup_node.md
```

Each entry should record:

```text
exists
size_bytes
included_in_export
status
```

### 8.2 completion_tree.txt

Example:

```text
⚝ wakeup.py
  exists: yes
  python_compile: pass
  export: yes

⚝ wakeup.sh
  exists: yes
  bash_syntax: pass
  executable: yes
  export: yes

⚝ README.md
  exists: yes
  required_sections: pass
  export: yes

⚝ runs/latest/wakeup_result.json
  exists: yes
  valid_json: yes
  export: yes

⚠︎ yfinance quote
  required: no
  degraded_allowed: yes
```

## 9. Export Gate

The export procedure shall package:

```text
wakeup.py
wakeup.sh
tickers.txt
README.md
tests/
docs/
completion_map.json
completion_tree.txt
runs/latest/wakeup_result.json
runs/wakeup_log.csv
```

Optional:

```text
runs/latest/ raw folder
```

Do not include:

```text
__pycache__/
.pytest_cache/
.env
API keys
private shell history
```

Recommended exported archive name:

```text
WO-004-C_wakeup_YYYY-MM-DD_HH-MM-SS_verified.zip
```

## 10. PowerShell Export Wrapper

The export may internally be a one-liner, but it should be wrapped tightly.

User-facing command:

```powershell
agent-export WO-004-C
```

Internal compact PowerShell shape:

```powershell
$stamp=Get-Date -Format "yyyy-MM-dd_HH-mm-ss";
$out="exports";
$stage=".leaf_export_staging";
New-Item -ItemType Directory -Force -Path $out,$stage | Out-Null;
Remove-Item $stage\* -Recurse -Force -ErrorAction SilentlyContinue;
foreach($p in @("wakeup.py","wakeup.sh","tickers.txt","README.md","tests","docs","completion_map.json","completion_tree.txt","runs\latest\wakeup_result.json","runs\wakeup_log.csv")){
  if(Test-Path $p){ Copy-Item $p -Destination $stage -Recurse -Force }
}
Compress-Archive -Path "$stage\*" -DestinationPath "$out\WO-004-C_wakeup_$stamp`_verified.zip" -Force;
Remove-Item $stage -Recurse -Force
```

This should eventually be hidden behind the CLI so humans do not have to paste a PowerShell centipede into the terminal. Humanity has suffered enough.

## 11. Symbolic Training Export Hook

WO-004-C should produce small training examples for LeafOS 0.8.0.

### 11.1 Unicode Form

```text
🍃 WO-004-C wakeup tails → print greeting with local time
⋆ WO-004-C wakeup heads → collect ticker payload and print offline analysis prompt
```

### 11.2 ASCII Alias Form

```text
@leaf.active WO-004-C wakeup tails -> print greeting with local time
@leaf.model WO-004-C wakeup heads -> collect ticker payload and print offline analysis prompt
```

### 11.3 Machine Action Form

```json
{
  "work_order": "WO-004-C",
  "action": "wakeup",
  "branch": "heads",
  "output_contract": "wakeup_stock_payload",
  "offline_analysis": true
}
```

## 12. Acceptance Criteria

This work order is complete when:

```text
tests/test_wakeup_shell.sh exists
tests/test_wakeup_json.py exists
docs/wakeup_node.md exists
README gate passes
tails branch test passes
heads branch test passes
JSON structure test passes
completion_map.json exists
completion_tree.txt exists
export archive is created
archive contains selected files only
symbolic training examples are documented or exported
```

Required verification commands:

```bash
bash tests/test_wakeup_shell.sh
python3 tests/test_wakeup_json.py runs/latest/wakeup_result.json
```

Optional export check:

```bash
unzip -l exports/WO-004-C_wakeup_*_verified.zip
```

## 13. Final State

When this work order passes:

```text
⚝ WO-004-C-02 verified
⎙ export completed
ꕤ WO-004-C checkpoint allowed
```

This finishes the ~C wakeup node as a stable LeafOS mini-module rather than just a script that says weird things about the afterlife and stocks. A low bar, but at least it clears it with logs.

## 14. 2026-07-19 Closeout

The export gate is available through `leafctl wakeup-export` on Bash and
PowerShell. The shell/JSON checks and selective archive gate pass; current
evidence is recorded in `reports/work-orders/WO-004-C-COMPLETION-REPORT.md`.
