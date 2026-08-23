#!/usr/bin/env sh
set -eu
SOURCE=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TARGET=${1:-"$HOME/.local/share/leafos"}
mkdir -p "$TARGET" "$HOME/.local/bin"
cp -R "$SOURCE/bin" "$SOURCE/core" "$SOURCE/config" "$SOURCE/packs" "$SOURCE/VERSION" "$TARGET/"
ln -sfn "$TARGET/bin/leafctl" "$HOME/.local/bin/leafctl"
"$HOME/.local/bin/leafctl" doctor
