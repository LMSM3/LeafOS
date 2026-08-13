#!/usr/bin/env bash
# Bash-native one-shot handoff bundle creator.

# shellcheck source=../ProjectLeaf/leafos_taskpack/core/brand/palette.sh
_BRAND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/ProjectLeaf/leafos_taskpack/core/brand"
if [[ -f "$_BRAND_DIR/palette.sh" ]]; then source "$_BRAND_DIR/palette.sh"; fi
unset _BRAND_DIR



set -euo pipefail

usage() {
  cat <<'HELP'
usage:
  ./oneshot.sh
  ./oneshot.sh --oneshot <source> <newlocation> [--force] [--no-zip]

Creates:
  README.md README.txt instructions.txt context.tex example.r infodata.xlsx
  run_demo.sh model_check.sh model_downloads.txt bundle_manifest.json
  stack_snapshot.txt leafos-oneshot.zip
HELP
}

banner() {
  printf '\n%s╔══════════════════════════════════════════════════════════════════════╗%s\n' "$C_SKY" "$C_RESET"
  printf '%s║                     LeafOS Bash OneShot Bundle                      ║%s\n' "$C_LEAF" "$C_RESET"
  printf '%s╚══════════════════════════════════════════════════════════════════════╝%s\n\n' "$C_SKY" "$C_RESET"
}

write_file() {
  local path="$1"
  local force="$2"
  if [[ -f "$path" && "$force" != "1" ]]; then
    printf '%s  ! kept existing %s%s\n' "$C_BUTTER" "$(basename "$path")" "$C_RESET"
    return
  fi
  cat > "$path"
  printf '%s  ✓ wrote %s%s\n' "$C_LEAF" "$(basename "$path")" "$C_RESET"
}

ONESHOT=0
FORCE=0
NOZIP=0
SOURCE=""
TARGET=""
POSITIONAL=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --oneshot) ONESHOT=1; shift ;;
    --force) FORCE=1; shift ;;
    --no-zip) NOZIP=1; shift ;;
    --source) SOURCE="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    --*) printf ' %s[?] unknown flag: %s%s\n' "$C_BUTTER" "$1" "$C_RESET" >&2; exit 2 ;;
    *) POSITIONAL+=("$1"); shift ;;
  esac
done

[[ -z "$SOURCE" && ${#POSITIONAL[@]} -ge 1 ]] && SOURCE="${POSITIONAL[0]}"
[[ -z "$TARGET" && ${#POSITIONAL[@]} -ge 2 ]] && TARGET="${POSITIONAL[1]}"

banner

if [[ "$ONESHOT" != "1" && ( -z "$SOURCE" || -z "$TARGET" ) ]]; then
  read -r -p "Source stack path [..]: " SOURCE
  SOURCE="${SOURCE:-..}"
  read -r -p "New bundle location: " TARGET
fi

[[ -n "$SOURCE" && -n "$TARGET" ]] || { usage; exit 2; }

SOURCE="$(cd "$SOURCE" && pwd)"
mkdir -p "$TARGET"
TARGET="$(cd "$TARGET" && pwd)"
CREATED_UTC="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
NAME="$(basename "$TARGET")"

printf '  ꕤ source: %s\n' "$SOURCE"
printf '  ꕤ target: %s\n' "$TARGET"

find "$SOURCE" -maxdepth 1 -mindepth 1 -printf '%y  %f\n' 2>/dev/null | head -80 > "$TARGET/stack_snapshot.txt" || true

write_file "$TARGET/README.md" "$FORCE" <<EOF
# $NAME

LeafOS Bash OneShot bundle created at \`$CREATED_UTC\`.

Source:

\`$SOURCE\`

## Quick start

\`\`\`bash
./run_demo.sh
\`\`\`

## If default models are missing

\`\`\`bash
./model_check.sh
./model_check.sh --resolve
./model_check.sh --resolve --apply --yes
\`\`\`

Apply is the download boundary.
EOF

write_file "$TARGET/README.txt" "$FORCE" <<EOF
$NAME

LeafOS Bash OneShot bundle created at $CREATED_UTC.

Run:
./run_demo.sh

If models are missing:
./model_check.sh
EOF

write_file "$TARGET/instructions.txt" "$FORCE" <<EOF
LeafOS Bash OneShot Instructions

A.) Installing

1. Open a Bash terminal.
2. cd "$TARGET"
3. Run: ./run_demo.sh

B.) Usage

Check model readiness:
  ./model_check.sh

Resolve metadata only:
  ./model_check.sh --resolve

Download/resume after review:
  ./model_check.sh --resolve --apply --yes
EOF

write_file "$TARGET/context.tex" "$FORCE" <<EOF
\documentclass{article}
\usepackage[margin=1in]{geometry}
\title{LeafOS Bash OneShot Context}
\date{$CREATED_UTC}
\begin{document}
\maketitle
\section*{Source}
\begin{verbatim}
$SOURCE
\end{verbatim}
\section*{Target}
\begin{verbatim}
$TARGET
\end{verbatim}
\section*{Safety}
Apply is the model download boundary.
\end{document}
EOF

write_file "$TARGET/example.r" "$FORCE" <<'EOF'
cat("LeafOS Bash OneShot bundle\n")
files <- c("README.md","README.txt","instructions.txt","context.tex",
           "example.r","infodata.xlsx","model_check.sh","model_downloads.txt")
print(data.frame(file = files, exists = file.exists(files)))
EOF

write_file "$TARGET/run_demo.sh" "$FORCE" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '\nLeafOS Bash OneShot bundle is ready.\n\n'
find . -maxdepth 1 -type f -printf '  %f\n' | sort
printf '\nIf models are missing, run:\n  ./model_check.sh\n'
EOF
chmod +x "$TARGET/run_demo.sh"

write_file "$TARGET/model_downloads.txt" "$FORCE" <<'EOF'
LeafOS model download decision sheet

Default runtime models:
- gemma4-coder Q4_K_M
- gemma4-opus-assistant Q4_K_M

Safe check:
  ./model_check.sh

Resolve metadata only:
  ./model_check.sh --resolve

Download/resume:
  ./model_check.sh --resolve --apply --yes
EOF

write_file "$TARGET/model_check.sh" "$FORCE" <<EOF
#!/usr/bin/env bash
set -euo pipefail
SOURCE_ROOT="$SOURCE"
if [[ -d "\$SOURCE_ROOT/ProjectLeaf/leaf_model_installer" ]]; then
  INSTALLER="\$SOURCE_ROOT/ProjectLeaf/leaf_model_installer"
elif [[ -d "\$(cd "\$SOURCE_ROOT/.." && pwd)/leaf_model_installer" ]]; then
  INSTALLER="\$(cd "\$SOURCE_ROOT/.." && pwd)/leaf_model_installer"
else
  echo "leaf_model_installer not found below or beside source root: \$SOURCE_ROOT" >&2
  exit 2
fi
PLANS_DIR="\$(cd "\$(dirname "\${BASH_SOURCE[0]}")" && pwd)/plans"
MODEL_DIR="\${LEAF_MODEL_DIR:-\$HOME/.leaf/models}"
RESOLVE=0
APPLY=0
YES=0
while [[ \$# -gt 0 ]]; do
  case "\$1" in
    --resolve) RESOLVE=1; shift ;;
    --apply) APPLY=1; shift ;;
    --yes) YES=1; shift ;;
    *) echo "unknown flag: \$1" >&2; exit 2 ;;
  esac
done
mkdir -p "\$PLANS_DIR"
PLAN="\$PLANS_DIR/leaf-runtime-plan.json"
RESOLVED="\$PLANS_DIR/leaf-runtime-plan.resolved.json"
leaf_models() {
  if command -v python3 >/dev/null 2>&1; then
    PYTHONPATH="\$INSTALLER\${PYTHONPATH:+:\$PYTHONPATH}" python3 -B -m leaf_models.install_cli "\$@"
  elif command -v python >/dev/null 2>&1; then
    PYTHONPATH="\$INSTALLER\${PYTHONPATH:+:\$PYTHONPATH}" python -B -m leaf_models.install_cli "\$@"
  else
    echo "python not found" >&2
    exit 2
  fi
}
leaf_models plan --profile runtime-default --dest "\$MODEL_DIR" --out "\$PLAN"
if [[ "\$RESOLVE" == "1" ]]; then leaf_models resolve "\$PLAN" --out "\$RESOLVED"; fi
if [[ "\$APPLY" == "1" ]]; then
  [[ "\$YES" == "1" ]] || { echo "apply downloads weights; add --yes" >&2; exit 2; }
  leaf_models apply "\$RESOLVED" --yes
fi
EOF
chmod +x "$TARGET/model_check.sh"

cat > "$TARGET/bundle_manifest.json" <<EOF
{
  "schema_version": 1,
  "surface": "Bash-Version",
  "name": "$NAME",
  "created_utc": "$CREATED_UTC",
  "source": "$SOURCE",
  "target": "$TARGET",
  "safety": "offline scaffold; apply requires --yes"
}
EOF

if command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; then
  PYBIN="$(command -v python3 || command -v python)"
  "$PYBIN" - "$TARGET/infodata.xlsx" "$CREATED_UTC" "$SOURCE" "$TARGET" <<'PY'
import sys, zipfile, html
path, created, source, target = sys.argv[1:5]
rows = [
    ("Field", "Value"),
    ("Created UTC", created),
    ("Source", source),
    ("Target", target),
    ("Mode", "bash oneshot"),
    ("Safety", "offline scaffold; apply requires yes"),
]
sheet_rows = []
for i, (a, b) in enumerate(rows, 1):
    sheet_rows.append(f'<row r="{i}"><c r="A{i}" t="inlineStr"><is><t>{html.escape(a)}</t></is></c><c r="B{i}" t="inlineStr"><is><t>{html.escape(b)}</t></is></c></row>')
with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml", '''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>''')
    z.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>''')
    z.writestr("xl/workbook.xml", '''<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="LeafOS Info" sheetId="1" r:id="rId1"/></sheets></workbook>''')
    z.writestr("xl/_rels/workbook.xml.rels", '''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>''')
    z.writestr("xl/worksheets/sheet1.xml", f'''<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>''')
PY
  printf '%s  ✓ wrote infodata.xlsx%s\n' "$C_LEAF" "$C_RESET"
fi

if [[ "$NOZIP" != "1" ]]; then
  "$PYBIN" - "$TARGET" "$TARGET/leafos-oneshot.zip" <<'PY'
import os, sys, zipfile
root, out = sys.argv[1:3]
if os.path.exists(out):
    os.remove(out)
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if os.path.isfile(path) and name != "leafos-oneshot.zip":
            z.write(path, name)
PY
  printf '%s  ✓ wrote leafos-oneshot.zip%s\n' "$C_LEAF" "$C_RESET"
fi

printf '\nOneShot complete: %s\n' "$TARGET"
