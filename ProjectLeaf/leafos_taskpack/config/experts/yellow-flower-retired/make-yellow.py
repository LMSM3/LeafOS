#!/usr/bin/env python3
import json, os, pathlib

base = pathlib.Path(r"C:\R\LeafOS0.2.1\ProjectLeaf\leafos_taskpack\config\experts\yellow")
base.mkdir(parents=True, exist_ok=True)

repo_qwen = "DavidAU/Qwen3.6-27B-Fable-Fusion-711-Uncensored-Heretic-NM-DAU-NEO-MAX-MTP-GGUF"
repo_helper = "GnLOLot/MiniCPM5-1B-Claude-Opus-Fable5-Thinking-GGUF"

def expert(**kwargs):
    purpose = kwargs.pop("purpose", "general LeafOS expert")
    notes = kwargs.pop("notes", "Placeholder until artifact is downloaded and revision pinned.")
    data = {
        "schema": "leafos.expert.v1",
        "source_repo": kwargs.get("source_repo", repo_qwen),
        "revision": kwargs.get("revision", "main"),
        "parameters_b": kwargs.get("parameters_b", 27),
        "provider": kwargs.get("provider", "llama.cpp"),
        "placement": kwargs.get("placement", "local"),
        "stack_segment": kwargs.get("stack_segment", "local_any"),
        "endpoint_ref": kwargs.get("endpoint_ref", "local-runtime"),
        "quantization": kwargs.get("quantization", "Q4_K_M"),
        "estimated_memory_gib": kwargs.get("estimated_memory_gib", 14.0),
        "context_tokens": kwargs.get("context_tokens", 32768),
        "capabilities": kwargs.get("capabilities", []),
        "fallback_chain": kwargs.get("fallback_chain", []),
        "enabled": kwargs.get("enabled", False),
        "purpose": purpose,
        "notes": notes,
        "install_state": {
            "status": "not_downloaded",
            "local_path": None,
            "blob_sha256": None,
            "verified": False,
            "download_attempts": 0
        },
        "runtime_params": {
            "flash_attention": True,
            "mmap": True,
            "mlock": False,
            "n_gpu_layers": -1 if kwargs.get("stack_segment") in ("local_gpu", "local_any") else 0,
            "seed": 42
        },
        "validation": {
            "launch_test_passed": False,
            "checksum_ok": False,
            "benchmark_tag": None
        }
    }
    data.update({k: v for k, v in kwargs.items() if k not in data or v is not None})
    (base / f"{data['id']}.json").write_text(json.dumps(data, indent=2) + "\n")

# Router
expert(id="yellow-router-fast", model_ref="qwen3.6-27b-fable", stack_segment="local_gpu",
       purpose="classify requests and reject incompatible lanes",
       quantization="IQ2_M_MTP", estimated_memory_gib=6.5, endpoint_ref="local-router",
       capabilities=["route.fast"], fallback_chain=["yellow-router-primary", "yellow-router-conservative"])
expert(id="yellow-router-primary", model_ref="qwen3.6-27b-fable", stack_segment="local_gpu",
       purpose="select primary lane and estimate task depth",
       quantization="IQ3_M_MTP", estimated_memory_gib=8.0, endpoint_ref="local-router",
       capabilities=["route.primary"], fallback_chain=["yellow-router-conservative"])
expert(id="yellow-router-conservative", model_ref="qwen3.6-27b-fable", stack_segment="local_cpu",
       purpose="reroute ambiguous tasks and recover from invalid route plans",
       quantization="IQ4_XS", estimated_memory_gib=10.0, endpoint_ref="local-router",
       capabilities=["route.conservative"], fallback_chain=["yellow-router-fast"])

# Brain
expert(id="yellow-brain-feeder", model_ref="qwen3.6-27b-fable", stack_segment="local_cpu",
       purpose="prepare context and divide tasks into reasoning packets",
       quantization="IQ4_XS", estimated_memory_gib=10.0, endpoint_ref="local-brain",
       capabilities=["proposal.review", "context.summarize"], fallback_chain=["yellow-brain-efficient"])
expert(id="yellow-brain-primary", model_ref="qwen3.6-27b-fable", stack_segment="local_gpu",
       purpose="primary planning, deep reasoning, and architecture decisions",
       quantization="Q6_K_MTP", estimated_memory_gib=22.0, endpoint_ref="local-brain",
       capabilities=["proposal.review", "route.plan"], fallback_chain=["yellow-brain-efficient", "yellow-brain-feeder"])
expert(id="yellow-brain-efficient", model_ref="qwen3.6-27b-fable", stack_segment="local_gpu",
       purpose="medium-cost reasoning when primary brain is occupied",
       quantization="Q5_K_M_MTP", estimated_memory_gib=18.0, endpoint_ref="local-brain",
       capabilities=["proposal.review"], fallback_chain=["yellow-brain-feeder"])
expert(id="yellow-brain-bedrock", model_ref="qwen3.6-27b-fable", stack_segment="local_cpu",
       purpose="high-confidence local review and overnight judgment",
       quantization="Q8_0_MTP", estimated_memory_gib=27.0, endpoint_ref="local-brain",
       capabilities=["proposal.review", "judge.local"], fallback_chain=["yellow-brain-primary"],
       notes="Runs on CPU segment; do not load casually into GPU on 48 GB hosts.")

# Code
expert(id="yellow-coder-fast", model_ref="qwen3.6-27b-fable", stack_segment="local_gpu",
       purpose="small patches, boilerplate, and rapid command construction",
       quantization="Q4_K_S", estimated_memory_gib=14.0, endpoint_ref="local-coder",
       capabilities=["proposal.patch", "diagnostic.compile"], fallback_chain=["yellow-coder-primary"])
expert(id="yellow-coder-primary", model_ref="qwen3.6-27b-fable", stack_segment="local_gpu",
       purpose="primary code generation and multi-file implementation",
       quantization="Q5_K_M", estimated_memory_gib=18.0, endpoint_ref="local-coder",
       capabilities=["proposal.patch", "diagnostic.compile", "diagnostic.lint"], fallback_chain=["yellow-coder-review", "yellow-coder-fast"])
expert(id="yellow-coder-review", model_ref="qwen3.6-27b-fable", stack_segment="local_gpu",
       purpose="review generated patches and detect API inconsistencies",
       quantization="Q6_K", estimated_memory_gib=22.0, endpoint_ref="local-coder",
       capabilities=["proposal.patch", "proposal.review"], fallback_chain=["yellow-coder-primary"])
expert(id="yellow-coder-bedrock", model_ref="qwen3.6-27b-fable", stack_segment="local_cpu",
       purpose="difficult debugging and final code arbitration",
       quantization="Q8_0", estimated_memory_gib=27.0, endpoint_ref="local-coder",
       capabilities=["proposal.patch", "proposal.review"], fallback_chain=["yellow-coder-review"])

# Critic
expert(id="yellow-critic-fast", model_ref="qwen3.6-27b-fable", stack_segment="local_gpu",
       purpose="detect obvious omissions and weak assumptions early",
       quantization="IQ4_NL", estimated_memory_gib=9.0, endpoint_ref="local-critic",
       capabilities=["proposal.review", "qa"], fallback_chain=["yellow-critic-primary"])
expert(id="yellow-critic-primary", model_ref="qwen3.6-27b-fable", stack_segment="local_gpu",
       purpose="challenge plans and search for contradictions",
       quantization="Q5_K_M", estimated_memory_gib=18.0, endpoint_ref="local-critic",
       capabilities=["proposal.review", "qa"], fallback_chain=["yellow-critic-bedrock"])
expert(id="yellow-critic-bedrock", model_ref="qwen3.6-27b-fable", stack_segment="local_cpu",
       purpose="final adversarial review and risky promotion inspection",
       quantization="Q8_0", estimated_memory_gib=27.0, endpoint_ref="local-critic",
       capabilities=["proposal.review", "qa", "judge.local"], fallback_chain=["yellow-critic-primary"])

# Writer
expert(id="yellow-writer-fast", model_ref="qwen3.6-27b-fable", stack_segment="local_gpu",
       purpose="short summaries, CLI help text, and changelog entries",
       quantization="Q4_K_M", estimated_memory_gib=14.0, endpoint_ref="local-writer",
       capabilities=["write.fast", "context.summarize"], fallback_chain=["yellow-writer-primary"])
expert(id="yellow-writer-primary", model_ref="qwen3.6-27b-fable", stack_segment="local_gpu",
       purpose="README files, work orders, and architecture documents",
       quantization="Q5_K_M", estimated_memory_gib=18.0, endpoint_ref="local-writer",
       capabilities=["write.primary", "context.summarize"], fallback_chain=["yellow-writer-bedrock"])
expert(id="yellow-writer-bedrock", model_ref="qwen3.6-27b-fable", stack_segment="local_cpu",
       purpose="final documentation review and publication-quality synthesis",
       quantization="Q8_0", estimated_memory_gib=27.0, endpoint_ref="local-writer",
       capabilities=["write.primary", "context.summarize"], fallback_chain=["yellow-writer-primary"])

# Judge local
expert(id="yellow-judge-local", model_ref="qwen3.6-27b-fable", stack_segment="local_gpu",
       purpose="evaluate candidate answers and score code patches",
       quantization="Q6_K", estimated_memory_gib=22.0, endpoint_ref="local-judge",
       capabilities=["judge.local", "proposal.review"], fallback_chain=["yellow-judge-bedrock"])
expert(id="yellow-judge-bedrock", model_ref="qwen3.6-27b-fable", stack_segment="local_cpu",
       purpose="rare high-precision arbitration and CPU final authority",
       quantization="F16", estimated_memory_gib=54.0, endpoint_ref="local-judge",
       capabilities=["judge.local", "judge.bedrock"], fallback_chain=["kimi-k27-code-remote", "deepseek-v3-qa-remote"],
       notes="Intentionally slow CPU-overflow model; never load casually into GPU.")

# HelperText
expert(id="yellow-helpertext-primary", model_ref="minicpm5-1b-fable", source_repo=repo_helper,
       parameters_b=1, stack_segment="local_gpu", quantization="Q8_0", estimated_memory_gib=2.0,
       endpoint_ref="local-helpertext", context_tokens=8192,
       purpose="rewrite command output and generate short user-facing text",
       capabilities=["write.fast"], fallback_chain=["yellow-helpertext-bedrock"])
expert(id="yellow-helpertext-bedrock", model_ref="minicpm5-1b-fable", source_repo=repo_helper,
       parameters_b=1, stack_segment="local_cpu", quantization="F16", estimated_memory_gib=3.5,
       endpoint_ref="local-helpertext", context_tokens=8192,
       purpose="precision-sensitive text normalization and wording repair",
       capabilities=["write.fast"], fallback_chain=["yellow-helpertext-primary"])
