# Debug Preparation for LeafOS 0.2.2

Local version bumped to **0.2.2**. This document is the starting point for a
thorough debug pass before any further release work.

## Version-authority changes made

| File | Was | Now |
|---|---|---|
| `VERSION` | 0.9.4 | 0.2.2 |
| `ProjectLeaf/leafos_taskpack/VERSION` | 0.9.4 | 0.2.2 |
| `leafos.root.json` | 0.9.4 | 0.2.2 |
| `README.md` badge | 0.9.4 | 0.2.2 |
| `README.md` snapshot text | 0.9.4 | 0.2.2 |
| `markdowns/README.md` | 0.9.4 | 0.2.2 |
| `LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.md` | 0.9.4 | 0.2.2 |
| `LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.formatless.tex` | 0.9.4 | 0.2.2 |

## Files intentionally NOT changed

- `ProjectLeaf/leafos_taskpack/tests/test_leaf_program.py`
  - Lines 26, 50, 51, 52 use 0.9.4 as test input data and verify the upgrade
	path to 0.2.2. Changing them would break the version-upgrade tests.

## Baseline test run

From `C:\R\LeafOS0.2.2`, capture the current baseline before fixing anything:

```powershell
bash test-all.sh 2>&1 | tee debug_0.2.2_baseline.log
# or, if using Python/pytest directly:
pytest ProjectLeaf/leafos_taskpack/tests -v 2>&1 | tee pytest_0.2.2_baseline.log
```

The 0.9.4 README reported: 214 passed, 10 failed, 49 errors. The first goal
of 0.2.2 debugging is to ensure the bump did not shift those numbers. The
second goal is to drive failures and errors toward zero.

## Isolated test groups

Run each group separately to attribute failures:

```powershell
# LeafOS program / version authority
pytest ProjectLeaf/leafos_taskpack/tests/test_leaf_program.py -v

# Continual Bloom runtime
pytest ProjectLeaf/leafos_taskpack/tests/test_continual_bloom.py -v

# Context runtime / agent loop / authority / economics
pytest ProjectLeaf/leafos_taskpack/tests/ -v \
  --ignore=ProjectLeaf/leafos_taskpack/tests/test_leaf_program.py
```

## Environment probes for debugging

```powershell
# Check Python environment
python --version
python -m pytest --version

# Check virtual environment
ProjectLeaf/.venv/Scripts/python.exe --version

# Verify version files
Get-Content VERSION
Get-Content ProjectLeaf/leafos_taskpack/VERSION
python -c "import json; print(json.load(open('leafos.root.json'))['version'])"
```

## Common failure categories to investigate

| Category | Typical cause | Quick check |
|---|---|---|
| Import/ModuleNotFound | Missing deps or bad `PYTHONPATH` | `python -c "import leaf_continual_bloom"` |
| Path mismatch | `ROOT` resolution in tests | `python -c "from pathlib import Path; print(Path('ProjectLeaf/leafos_taskpack/core/python/leaf_continual_bloom.py').resolve().parents[2])"` |
| JSON schema mismatch | Out-of-date contract file | Validate `config/continual-bloom-monday.json` |
| Version-badge test | Regex or shield mismatch | `pytest tests/test_leaf_program.py` |
| Permission / atomic write | Windows path locking | Run tests with an isolated `HOME` temp dir |

## Capturing evidence

For each failure, capture:

1. Test name and traceback.
2. Host state: RAM, disk, Python version, shell.
3. Reproduction command.
4. Whether the failure exists at 0.9.4 (use git stash/checkout if needed).

Use this template for new issues:

```text
FAIL: <test.py>::<TestClass>::<test_method>
ERROR: <last 5 lines of traceback>
REPRO: <exact command>
ENV: <python version, windows/linux, ram>
NOTES: <any observations>
```

## LeafOS Monday sanity check

```powershell
cd ProjectLeaf/leafos_taskpack
python core/python/leaf_continual_bloom.py status --json
# expected: schema leafos.continual_bloom_state, status not_initialized initially
python core/python/leaf_continual_bloom.py init
python core/python/leaf_continual_bloom.py input --text "Debug pass start"
python core/python/leaf_continual_bloom.py status --json
```

## Safe rollback

If 0.2.2 debugging needs to be abandoned, the touched files can be reverted:

```powershell
# Or use git checkout if the repo is clean
Get-ChildItem -Recurse -File | Select-String -Pattern "0\.9\.5"
```

## Notes

- Do not run `program.ps1 change-version` against these files unless you want
  it to rewrite README shields and re-synchronize brand assets; the manual bump
  here is intentional and minimal.
- FlowerOS context-runtime work is separate; keep LeafOS 0.2.2 validation
  scoped to the `LeafOS0.2.2` directory.
