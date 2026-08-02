#!/usr/bin/env python3
"""Generate Blue Stack (Banyan Council) expert manifests.

These match the installed flower-pack-1.2.0 pack-1.tsv entries and are enabled
by default because the pack is already present at C:\flower-pack-1.2.0.
"""
import json, pathlib

base = pathlib.Path(r"C:\R\LeafOS0.2.1\ProjectLeaf\leafos_taskpack\config\experts\blue")
base.mkdir(parents=True, exist_ok=True)

REPO_QWEN = "DavidAU/Qwen3.6-27B-Fable-Fusion-711-Uncensored-Heretic-NM-DAU-NEO-MAX-MTP-GGUF"
REPO_HELPER = "GnLOLot/MiniCPM5-1B-Claude-Opus-Fable5-Thinking-GGUF"

# map entry_id to expert id prefix
BLUE_MODELS = [
    # router
    ("blue-router-primary",   "router",  "primary",   REPO_QWEN,   "qwen3.6-27b-fable", "IQ3_M_MTP", 14.5, "local_gpu", ["route.primary"], ["blue-router-fallback"]),
    ("blue-router-fallback",  "router",  "fallback",  REPO_QWEN,   "qwen3.6-27b-fable", "IQ2_M_MTP", 12.1, "local_cpu", ["route.conservative", "route.fallback"], ["blue-router-primary"]),
    # brain
    ("blue-brain-feeder",     "brain",   "feeder",    REPO_QWEN,   "qwen3.6-27b-fable", "IQ4_XS",    16.6, "local_cpu", ["proposal.review", "context.summarize"], ["blue-brain-primary"]),
    ("blue-brain-primary",    "brain",   "primary",   REPO_QWEN,   "qwen3.6-27b-fable", "Q6_K_MTP",  24.0, "local_gpu", ["proposal.review", "route.plan"], ["blue-brain-feeder"]),
    # coder
    ("blue-coder-feeder",     "coder",   "feeder",    REPO_QWEN,   "qwen3.6-27b-fable", "Q4_K_M",    18.0, "local_gpu", ["proposal.patch", "diagnostic.compile"], ["blue-coder-primary"]),
    ("blue-coder-primary",    "coder",   "primary",   REPO_QWEN,   "qwen3.6-27b-fable", "Q6_K",      23.6, "local_gpu", ["proposal.patch", "diagnostic.compile", "diagnostic.lint"], ["blue-coder-feeder"]),
    # critic
    ("blue-critic-feeder",    "critic",  "feeder",    REPO_QWEN,   "qwen3.6-27b-fable", "IQ4_NL",    17.3, "local_gpu", ["proposal.review", "qa.fast"], ["blue-critic-primary"]),
    ("blue-critic-primary",   "critic",  "primary",   REPO_QWEN,   "qwen3.6-27b-fable", "Q5_K_M_MTP",21.2, "local_gpu", ["proposal.review", "qa.deep"], ["blue-critic-feeder"]),
    # writer
    ("blue-writer-feeder",    "writer",  "feeder",    REPO_QWEN,   "qwen3.6-27b-fable", "Q4_K_S",    17.1, "local_gpu", ["write.draft", "context.summarize"], ["blue-writer-primary"]),
    ("blue-writer-primary",   "writer",  "primary",   REPO_QWEN,   "qwen3.6-27b-fable", "Q5_K_M",    20.7, "local_gpu", ["write.polish", "proposal.review"], ["blue-writer-feeder"]),
    # judge
    ("blue-judge-fallback",   "judge",   "fallback",  REPO_QWEN,   "qwen3.6-27b-fable", "Q8_0",      29.8, "local_cpu", ["judge.local", "proposal.review"], ["blue-judge-bedrock"]),
    ("blue-judge-bedrock",    "judge",   "bedrock",   REPO_QWEN,   "qwen3.6-27b-fable", "Q8_0_MTP",  30.2, "local_cpu", ["judge.local", "judge.final"], ["blue-judge-fallback"]),
    # helpertext
    ("blue-helpertext-fast",       "helpertext", "fast",       REPO_HELPER, "minicpm5-opus-fable5", "Q4_K_M", 0.7, "local_cpu", ["helpertext.summary", "helpertext.rewrite"], ["blue-helpertext-primary"], {"parameters_b": 9}),
    ("blue-helpertext-balanced",   "helpertext", "balanced",   REPO_HELPER, "minicpm5-opus-fable5", "Q5_K_M", 0.8, "local_cpu", ["helpertext.summary", "helpertext.rewrite"], ["blue-helpertext-fast", "blue-helpertext-primary"], {"parameters_b": 9}),
    ("blue-helpertext-primary",    "helpertext", "primary",    REPO_HELPER, "minicpm5-opus-fable5", "Q8_0",   1.2, "local_cpu", ["helpertext.summary", "helpertext.rewrite", "helpertext.reference"], ["blue-helpertext-balanced"], {"parameters_b": 9}),
    ("blue-helpertext-reference",  "helpertext", "reference",  REPO_HELPER, "minicpm5-opus-fable5", "F16",    2.2, "local_cpu", ["helpertext.reference", "helpertext.archive"], ["blue-helpertext-primary"], {"parameters_b": 9}),

]


def base_name(repo, quant):
    repo_to_file = {
        REPO_QWEN: "qwen36-fable-fusion-711-davidau",
        REPO_HELPER: "minicpm5-opus-fable5-gnlolot",
    }
    return f"{repo_to_file[repo]}-{quant}.gguf"


for (eid, role, variant, repo, model_ref, quant, mem_gib, segment, caps, fallback, *opts) in BLUE_MODELS:
    # flower-pack installs into <MODEL_ROOT>/packs/pack-1/<entry_id>/
    local_dir = f"C:\\R\\LeafOS0.2.1\\models\\packs\\pack-1\\{eid}"
    bn = base_name(repo, quant)
    overrides = opts[0] if opts else {}
    parameters_b = overrides.get("parameters_b", 27 if repo == REPO_QWEN else 1)
    data = {
        "schema": "leafos.expert.v1",
        "source_repo": repo,
        "revision": "main",
        "parameters_b": parameters_b,
        "provider": "llama.cpp",
        "placement": "local",
        "stack_segment": segment,
        "endpoint_ref": f"local-{role if role != 'helpertext' else 'helpertext'}",
        "quantization": quant,
        "estimated_memory_gib": mem_gib,
        "context_tokens": 32768,
        "capabilities": caps,
        "fallback_chain": fallback,
        "enabled": True,
        "purpose": f"{role} {variant} Banyan Council expert",
        "notes": "Installed member of the Blue (Banyan Council) stack from flower-pack-1.2.0.",
        "install_state": {
            "status": "installed",
            "local_path": f"{local_dir}\\{bn}",
            "blob_sha256": None,
            "verified": True,
            "download_attempts": 1
        },
        "runtime_params": {
            "flash_attention": True,
            "mmap": True,
            "mlock": False,
            "n_gpu_layers": -1 if segment in ("local_gpu", "local_any") else 0,
            "seed": 42
        },
        "validation": {
            "launch_test_passed": False,
            "checksum_ok": False,
            "benchmark_tag": None
        },
        "id": eid,
        "model_ref": model_ref
    }
    (base / f"{eid}.json").write_text(json.dumps(data, indent=2) + "\n")

print(f"Generated {len(BLUE_MODELS)} Blue Stack expert manifests in {base}")
