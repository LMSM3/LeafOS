#!/usr/bin/env bash
# bin/install_mac.sh -- macOS-specific LeafOS installer
# Usage: ./bin/install_mac.sh [PREFIX]
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$(uname -s)" != Darwin ]]; then
    echo "This installer is macOS-only. Use install_demo.sh on Linux/WSL." >&2
    exit 1
fi

# source brand helpers early for colored output
# shellcheck disable=SC1090
source "$ROOT_DIR/core/brand/brand.sh"

MACOS_VER="$(sw_vers -productVersion)"

if [[ "${1:-}" ]]; then
    PREFIX="$1"
elif [[ -w /usr/local ]]; then
    PREFIX=/usr/local
else
    PREFIX="$HOME/.local"
fi

SHARE_DIR="$PREFIX/share/leafos"
BIN_DIR="$PREFIX/bin"

brand_banner
brand_header "LeafOS macOS Installer"
brand_kv "macOS"  "$MACOS_VER"
brand_kv "prefix" "$PREFIX"
brand_kv "share"  "$SHARE_DIR"
brand_kv "bin"    "$BIN_DIR"
printf '\n'

command -v brew &>/dev/null || brand_warn "Homebrew not found — some optional features unavailable."

mkdir -p "$SHARE_DIR" "$BIN_DIR"

source "$ROOT_DIR/core/loaders/loaders.sh"
leaf_loader_run_timed \
    rsync -a --exclude='.git' --exclude='build' "$ROOT_DIR/" "$SHARE_DIR/" \
    "Copying files" orbit 0.10

for tool in leafctl flowerctl leafpy; do
    src="$SHARE_DIR/bin/$tool"
    dst="$BIN_DIR/$tool"
    [[ -f "$src" ]] || continue
    chmod +x "$src"
    ln -sf "$src" "$dst"
    brand_ok "linked $dst"
done
ln -sf "$SHARE_DIR/bin/leafctl" "$BIN_DIR/leaf"
ln -sf "$SHARE_DIR/bin/flowerctl" "$BIN_DIR/leafos"
ln -sf "$SHARE_DIR/bin/flowerctl" "$BIN_DIR/flower"
brand_ok "linked quick commands: leafos, leaf, flower"

if command -v make &>/dev/null && [[ -f "$SHARE_DIR/Makefile" ]]; then
    leaf_loader_run_timed \
        bash -c "make -C \"$SHARE_DIR\" -s 2>/dev/null" \
        "Building C demos" blade 0.09 \
        || bash "$SHARE_DIR/bin/build_c_demo.sh"
elif command -v cc &>/dev/null || command -v gcc &>/dev/null || command -v clang &>/dev/null; then
    leaf_loader_run_timed \
        bash "$SHARE_DIR/bin/build_c_demo.sh" \
        "Building C demos (fallback)" blade 0.09
fi

SHELL_RC=""
case "$SHELL" in */zsh)  SHELL_RC="$HOME/.zshrc" ;; */bash) SHELL_RC="$HOME/.bash_profile" ;; esac

if [[ -n "$SHELL_RC" ]] && ! grep -q "leafos" "$SHELL_RC" 2>/dev/null; then
    printf '\n'
    brand_say "Add to $SHELL_RC:"
    brand_kv "  export" "PATH=\"$BIN_DIR:\$PATH\""
    printf '\n  %sAppend automatically? [y/N]%s ' "$C_BOLD" "$C_RESET"
    read -r yn
    if [[ "$yn" == [yY] ]]; then
        printf '\n# LeafOS\nexport PATH="%s:$PATH"\n' "$BIN_DIR" >> "$SHELL_RC"
        brand_ok "Added. Restart shell or: source $SHELL_RC"
    fi
fi

printf '\n'
brand_kv "quick syntax" "leafos q"
brand_kv "home" "leafos"
brand_kv "full help" "leafos help"
printf '\n'

# --- post-install: model grab + CUDA/deps loop
POST="$SHARE_DIR/bin/post_install.sh"
if [[ -f "$POST" ]]; then
    bash "$POST"
else
    brand_say "Post-install script not found at $POST -- skipping."
fi
