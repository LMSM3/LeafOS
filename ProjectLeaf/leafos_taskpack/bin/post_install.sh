#!/usr/bin/env bash
# bin/post_install.sh -- post-install: optional HF model grab + CUDA/deps loop
#
# Usage: bash bin/post_install.sh [--noninteractive]
#
# Environment overrides:
#   LEAF_SKIP_MODELS=1   skip model prompt entirely
#   LEAF_SKIP_CUDA=1     skip CUDA/deps loop
#   LEAF_MODEL_DIR       model storage path  (default ~/.leaf/models)
#   LEAF_MODEL_PROFILE   runtime-default | default | extended | experimental
#   LEAF_MODEL_PLAN      output path for the offline plan
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$ROOT_DIR/core/brand/brand.sh"
source "$ROOT_DIR/core/loaders/loaders.sh"

NONINTERACTIVE="${1:-}"
[[ "$NONINTERACTIVE" == "--noninteractive" ]] && NONINTERACTIVE=1 || NONINTERACTIVE=0

LEAF_SKIP_MODELS="${LEAF_SKIP_MODELS:-0}"
LEAF_SKIP_CUDA="${LEAF_SKIP_CUDA:-0}"
LEAF_MODEL_DIR="${LEAF_MODEL_DIR:-$HOME/.leaf/models}"
LEAF_MODEL_PROFILE="${LEAF_MODEL_PROFILE:-runtime-default}"
LEAF_MODEL_PLAN="${LEAF_MODEL_PLAN:-$HOME/.leaf/model-install-plan.json}"

# ---------------------------------------------------------------------------
# Dependency catalogue  (kind: apt | pip)
# ---------------------------------------------------------------------------
DEPS_LABEL=(
    "CUDA Toolkit 12.4"
    "cuDNN 9 (CUDA 12)"
    "NVIDIA Container Toolkit"
    "Python build essentials"
    "llama-cpp-python (GPU)"
    "huggingface_hub CLI"
    "PyTorch with CUDA 12.4"
)
DEPS_KIND=(  apt apt apt apt pip pip pip )

DEPS_APT=(
    "cuda-toolkit-12-4"
    "libcudnn9-dev-cuda-12"
    "nvidia-container-toolkit"
    "build-essential python3-dev python3-pip"
    "" "" ""
)
DEPS_PIP=(
    "" "" "" ""
    "CMAKE_ARGS=-DLLAMA_CUDA=on pip install llama-cpp-python --upgrade --quiet"
    "pip install huggingface_hub --quiet"
    "pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 --quiet"
)

# ---------------------------------------------------------------------------
_detect_pkg_manager() {
    command -v apt-get &>/dev/null && echo apt && return
    command -v brew    &>/dev/null && echo brew && return
    echo none
}

# ---------------------------------------------------------------------------
# SECTION 1 — canonical model installation plan
# ---------------------------------------------------------------------------
_post_install_models() {
    brand_header "Optional: LeafOS Model Installation Plan"

    if [[ "$LEAF_SKIP_MODELS" == "1" ]]; then
        brand_say "Model planning skipped (LEAF_SKIP_MODELS=1)."
        return 0
    fi

    local launcher="$ROOT_DIR/bin/leaf-models"
    [[ -f "$launcher" ]] || {
        brand_warn "Canonical model installer is unavailable: $launcher"
        return 1
    }

    mkdir -p "$(dirname "$LEAF_MODEL_PLAN")"
    bash "$launcher" plan \
        --profile "$LEAF_MODEL_PROFILE" \
        --dest "$LEAF_MODEL_DIR" \
        --out "$LEAF_MODEL_PLAN" || return 1

    brand_ok "Model installation plan created; no weights were downloaded."
    brand_kv "plan" "$LEAF_MODEL_PLAN"
    brand_kv "next" "leafctl models-install resolve $LEAF_MODEL_PLAN"
    return 0
}

# ---------------------------------------------------------------------------
# SECTION 2 — CUDA and runtime dependencies
# ---------------------------------------------------------------------------
_post_install_cuda() {
    brand_header "CUDA & Runtime Dependencies"

    if [[ "$LEAF_SKIP_CUDA" == "1" ]]; then
        brand_say "CUDA/deps skipped (LEAF_SKIP_CUDA=1)."
        return 0
    fi

    local pkgmgr; pkgmgr="$(_detect_pkg_manager)"
    brand_kv "package manager" "$pkgmgr"

    if command -v nvidia-smi &>/dev/null; then
        brand_ok "NVIDIA GPU detected:"
        nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null \
        | while IFS=',' read -r gpuname drv; do
            brand_kv "  GPU"    "$(printf '%s' "$gpuname" | xargs)"
            brand_kv "  driver" "$(printf '%s' "$drv"     | xargs)"
          done
    else
        printf '\n'
        brand_warn "nvidia-smi not found — CUDA packages may not function."
        if [[ "$NONINTERACTIVE" != "1" ]]; then
            printf '  %sContinue anyway? [y/N]%s ' "$C_YELLOW_B" "$C_RESET"
            local ans; read -r ans
            [[ "${ans:-n}" == [yY] ]] || { brand_say "CUDA deps skipped."; return 0; }
        fi
    fi

    printf '\n'
    local total=${#DEPS_LABEL[@]}
    local i rc=0
    for ((i=0; i<total; i++)); do
        local label="${DEPS_LABEL[$i]}"
        local kind="${DEPS_KIND[$i]}"
        local apt_pkg="${DEPS_APT[$i]}"
        local pip_cmd="${DEPS_PIP[$i]}"

        leaf_progress_bar $((i+1)) "$total" "($((i+1))/$total) $label"
        printf '\n'

        case "$kind" in
            apt)
                if [[ "$pkgmgr" != "apt" || -z "$apt_pkg" ]]; then
                    [[ -z "$apt_pkg" ]] || brand_warn "$label needs apt, got $pkgmgr — skipping."
                    continue
                fi
                if leaf_loader_run_timed \
                       bash -c "DEBIAN_FRONTEND=noninteractive apt-get install -y $apt_pkg" \
                       "$label" orbit 0.10; then
                    : # success shown by timed loader
                else
                    brand_warn "$label install failed (non-fatal)."
                    rc=1
                fi
                ;;
            pip)
                if [[ -z "$pip_cmd" ]]; then continue; fi
                if ! command -v pip &>/dev/null && ! command -v pip3 &>/dev/null; then
                    brand_warn "pip not found — skipping $label."
                    continue
                fi
                if leaf_loader_run_timed \
                       bash -c "$pip_cmd" \
                       "$label" braille 0.08; then
                    :
                else
                    brand_warn "$label install failed (non-fatal)."
                    rc=1
                fi
                ;;
        esac
    done

    printf '\n'
    if [[ $rc -eq 0 ]]; then
        brand_ok "CUDA / runtime dependency pass complete."
    else
        brand_warn "Some dependencies failed — check output above and retry."
    fi
    return $rc
}

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
_post_install_main() {
    brand_banner

    brand_header "LeafOS Post-Install Setup"
    brand_kv "models dir"   "$LEAF_MODEL_DIR"
    brand_kv "model profile" "$LEAF_MODEL_PROFILE"
    brand_kv "skip models"  "$LEAF_SKIP_MODELS"
    brand_kv "skip CUDA"    "$LEAF_SKIP_CUDA"
    printf '\n'

    if [[ "$NONINTERACTIVE" != "1" ]]; then
        printf '  %sRun post-install setup now? [Y/n]%s ' "$C_BOLD" "$C_RESET"
        local ans; read -r ans
        case "${ans:-y}" in
            [nN]) brand_say "Post-install skipped. Re-run: bash bin/post_install.sh"; exit 0 ;;
        esac
    fi

    _post_install_models || {
        brand_warn "Model planning failed; post-install is incomplete."
        return 1
    }
    printf '\n'
    _post_install_cuda || {
        brand_warn "Some runtime dependencies failed; post-install is incomplete."
        return 1
    }
    printf '\n'

    brand_header "Post-Install Complete"
    brand_ok "LeafOS is ready."
    brand_kv "models"  "$LEAF_MODEL_DIR"
    brand_kv "quick syntax" "leafos q"
    brand_kv "home"    "leafos"
    brand_kv "full help" "leafos help"
    printf '\n'
}

_post_install_main "$@"
