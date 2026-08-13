#!/usr/bin/env bash
# core/agent/agent.sh
# CLI-first agentic coding helpers.
# This module does not call remote APIs. It creates auditable task files,
# command plans, dry-runs, validation passes, and guarded local execution.

set -euo pipefail

AGENT_ROOT="${AGENT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
AGENT_CONFIG="${AGENT_CONFIG:-$AGENT_ROOT/config/agents.conf}"

if [[ -f "$AGENT_CONFIG" ]]; then
    # shellcheck source=/dev/null
    source "$AGENT_CONFIG"
fi

PROVIDER_CONFIG="${PROVIDER_CONFIG:-$AGENT_ROOT/config/providers.conf}"
if [[ -f "$PROVIDER_CONFIG" ]]; then
    # shellcheck source=/dev/null
    source "$PROVIDER_CONFIG"
fi
source "$AGENT_ROOT/core/providers/providers.sh"

DEFAULT_AGENT_PROFILE="${DEFAULT_AGENT_PROFILE:-local-coder}"
AGENT_PLAN_DIR="${AGENT_PLAN_DIR:-tasks}"
AGENT_REPORT_DIR="${AGENT_REPORT_DIR:-reports}"
AGENT_SAFE_MODE="${AGENT_SAFE_MODE:-1}"
AGENT_REQUIRE_CONFIRM="${AGENT_REQUIRE_CONFIRM:-1}"
AGENT_PROFILES="${AGENT_PROFILES:-planner local-coder reviewer shell-guardian}"
AGENT_PLAN_VERSION="${AGENT_PLAN_VERSION:-0.2.0}"

agent_profile_summary() {
    local name="$1"
    case "$name" in
        planner)
            printf '%s\t%s\n' "planner" "turns vague requests into small auditable work orders"
            ;;
        local-coder)
            printf '%s\t%s\n' "local-coder" "writes local shell/C patches and leaves a paper trail"
            ;;
        reviewer)
            printf '%s\t%s\n' "reviewer" "checks diffs, smoke tests, and obvious foot-guns"
            ;;
        shell-guardian)
            printf '%s\t%s\n' "shell-guardian" "blocks destructive commands unless explicitly allowed"
            ;;
        *)
            printf '%s\t%s\n' "$name" "custom profile"
            ;;
    esac
}

agent_list_profiles() {
    local p
    for p in $AGENT_PROFILES; do
        agent_profile_summary "$p"
    done
}

agent_slug() {
    local raw="$*"
    local slug
    slug="$(printf '%s' "$raw" | LC_ALL=C tr '[:upper:]' '[:lower:]' | LC_ALL=C tr -cs 'a-z0-9' '-')"
    slug="${slug#-}"
    slug="${slug%-}"
    slug="${slug:0:80}"
    slug="${slug%-}"
    [[ -n "$slug" ]] || slug="task"
    printf '%s' "$slug"
}

agent_task_validate() {
    local task_file="${1:-}"
    [[ -n "$task_file" ]] || return 2
    [[ -f "$task_file" ]] || {
        printf 'missing task file: %s\n' "$task_file" >&2
        return 1
    }

    local bad=0 section
    for section in Title Scope Steps; do
        if ! grep -q "^## ${section}$" "$task_file"; then
            printf 'invalid task: missing ## %s\n' "$section" >&2
            bad=1
        fi
    done

    for section in Title Scope Steps; do
        if ! awk -v section="$section" '
            $0 == "## " section { in_section=1; next }
            in_section && /^## / { exit }
            in_section && NF { found=1 }
            END { exit(found ? 0 : 1) }
        ' "$task_file"; then
            printf 'invalid task: %s section is empty\n' "$section" >&2
            bad=1
        fi
    done

    [[ "$bad" -eq 0 ]]
}

_agent_render_template() {
    local template="$1" output="$2" title="$3" slug="$4" created_at="$5" task_file="${6:-}" plan_name="${7:-}"
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line//\{\{TITLE\}\}/$title}"
        line="${line//\{\{SLUG\}\}/$slug}"
        line="${line//\{\{CREATED_AT\}\}/$created_at}"
        line="${line//\{\{TASK_FILE\}\}/$task_file}"
        line="${line//\{\{TASK_SLUG\}\}/$slug}"
        line="${line//\{\{PLAN_NAME\}\}/$plan_name}"
        printf '%s\n' "$line"
    done < "$template" > "$output"
}

agent_task_new() {
    local title="$*"
    [[ -n "$title" ]] || return 2
    [[ "$title" != *$'\n'* && "$title" != *$'\r'* ]] || {
        printf 'task title must be a single line\n' >&2
        return 2
    }

    local slug path now
    slug="$(agent_slug "$title")"
    path="$AGENT_ROOT/$AGENT_PLAN_DIR/$slug.md"
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    [[ ! -e "$path" ]] || {
        printf 'task exists: %s\n' "$path" >&2
        return 1
    }

    mkdir -p "$(dirname "$path")"
    local tmp="${path}.tmp.$$"
    _agent_render_template \
        "$AGENT_ROOT/share/templates/agent_task.md.tpl" \
        "$tmp" "$title" "$slug" "$now"
    if ! agent_task_validate "$tmp" >/dev/null 2>&1; then
        rm -f "$tmp"
        printf 'generated task failed template validation\n' >&2
        return 1
    fi
    mv "$tmp" "$path"

    printf '%s\n' "$path"
}

agent_plan_new() {
    local task_file="${1:-}"
    local plan_name="${2:-plan}"
    [[ -n "$task_file" ]] || return 2
    [[ -f "$task_file" ]] || {
        printf 'missing task file: %s\n' "$task_file" >&2
        return 1
    }
    agent_task_validate "$task_file" || return 1

    local base plan_path now
    base="$(basename "$task_file" .md)"
    plan_path="$AGENT_ROOT/$AGENT_PLAN_DIR/$base.$(agent_slug "$plan_name").plan.sh"
    now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

    [[ ! -e "$plan_path" ]] || {
        printf 'plan exists: %s\n' "$plan_path" >&2
        return 1
    }

    local tmp="${plan_path}.tmp.$$"
    _agent_render_template \
        "$AGENT_ROOT/share/templates/agent_plan.sh.tpl" \
        "$tmp" "" "$(agent_slug "$base")" "$now" "$task_file" "$plan_name"
    chmod +x "$tmp"
    if ! agent_plan_validate "$tmp" >/dev/null 2>&1; then
        rm -f "$tmp"
        printf 'generated plan failed validation\n' >&2
        return 1
    fi
    mv "$tmp" "$plan_path"
    printf '%s\n' "$plan_path"
}

# agent_plan_generate TASK_FILE [PLAN_NAME] -- route task to provider, write filled plan.
# Unlike agent_plan_new (which writes a blank template), this calls leaf_provider_route
# and writes the generated content. Validates and prints the plan path on success.
agent_plan_generate() {
    local task_file="${1:-}"
    local plan_name="${2:-generated}"
    [[ -n "$task_file" ]] || return 2
    [[ -f "$task_file" ]] || {
        printf 'missing task file: %s\n' "$task_file" >&2
        return 1
    }
    agent_task_validate "$task_file" || return 1

    local base plan_path now
    base="$(basename "$task_file" .md)"
    plan_path="$AGENT_ROOT/$AGENT_PLAN_DIR/$base.$(agent_slug "$plan_name").plan.sh"
    now="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

    [[ ! -e "$plan_path" ]] || {
        printf 'plan exists: %s\n' "$plan_path" >&2
        return 1
    }

    mkdir -p "$(dirname "$plan_path")"
    local tmp="${plan_path}.tmp.$$"
    if ! leaf_provider_route "$task_file" > "$tmp"; then
        rm -f "$tmp"
        printf 'provider failed; generated plan discarded\n' >&2
        return 1
    fi
    chmod +x "$tmp"

    # Validate immediately -- refuse to deliver a plan that would fail validation.
    if ! agent_plan_validate "$tmp" >/dev/null 2>&1; then
        rm -f "$tmp"
        printf 'generated plan failed validation; discarded\n' >&2
        return 1
    fi
    mv "$tmp" "$plan_path"

    printf '%s\n' "$plan_path"
}

agent_plan_validate() {
    local plan="${1:-}"
    [[ -n "$plan" ]] || return 2
    [[ -f "$plan" ]] || {
        printf 'missing plan: %s\n' "$plan" >&2
        return 1
    }

    local bad=0

    if ! grep -q '^#!/usr/bin/env bash$' "$plan"; then
        printf 'invalid: missing bash shebang\n' >&2
        bad=1
    fi

    if ! grep -q '^# LEAFOS_AGENT_PLAN=1' "$plan"; then
        printf 'invalid: missing LEAFOS_AGENT_PLAN marker\n' >&2
        bad=1
    fi

    if grep -q '^# LEAFOS_AGENT_PLAN_VERSION=' "$plan" && \
       ! grep -q "^# LEAFOS_AGENT_PLAN_VERSION=${AGENT_PLAN_VERSION}$" "$plan"; then
        printf 'invalid: unsupported agent plan version\n' >&2
        bad=1
    fi

    if ! grep -q '^run_step[[:space:]]' "$plan"; then
        printf 'invalid: plan has no run_step commands\n' >&2
        bad=1
    fi

    if ! bash -n "$plan" 2>/dev/null; then
        printf 'invalid: plan has shell syntax errors\n' >&2
        bad=1
    fi

    if grep -nE '\b(rm[[:space:]]+-rf|mkfs|dd[[:space:]]+if=|shutdown|reboot|:(){|chmod[[:space:]]+777|curl[^|;]*\|[[:space:]]*sh|wget[^|;]*\|[[:space:]]*sh)\b' "$plan" >&2; then
        printf 'invalid: destructive or pipe-to-shell pattern found\n' >&2
        bad=1
    fi

    if grep -nE '(^|[;&|])[[:space:]]*sudo\b' "$plan" >&2; then
        printf 'invalid: sudo is not allowed in agent plans\n' >&2
        bad=1
    fi

    [[ "$bad" -eq 0 ]]
}

agent_plan_dry_run() {
    local plan="${1:-}"
    shift || true
    local format="normal" arg
    while [[ $# -gt 0 ]]; do
        arg="$1"
        case "$arg" in
            --plain) format="plain" ;;
            --json) format="json" ;;
            --format=normal|--format=plain|--format=json) format="${arg#--format=}" ;;
            --format)
                [[ $# -ge 2 ]] || { printf 'agent dry-run: --format requires normal, plain, or json\n' >&2; return 2; }
                format="$2"
                shift
                ;;
            *) printf 'agent dry-run: unknown option: %s\n' "$arg" >&2; return 2 ;;
        esac
        shift
    done

    agent_plan_validate "$plan"
    local -a steps=()
    while IFS= read -r step; do
        [[ -n "$step" ]] && steps+=("$step")
    done < <(awk '/^run_step[[:space:]]/ { sub(/^run_step[[:space:]]+/, ""); print }' "$plan")

    case "$format" in
        normal)
            printf 'dry-run plan: %s\n' "$plan"
            for step in "${steps[@]}"; do
                printf '%s\n' "  would run: $step"
            done
            ;;
        plain)
            printf '%s\n' "${steps[@]}"
            ;;
        json)
            printf '{"plan":'
            _agent_json_string "$plan"
            printf ',"steps":['
            local first=1
            for step in "${steps[@]}"; do
                [[ "$first" -eq 1 ]] || printf ','
                _agent_json_string "$step"
                first=0
            done
            printf ']}\n'
            ;;
        *)
            printf 'agent dry-run: unsupported format: %s\n' "$format" >&2
            return 2
            ;;
    esac
}

_agent_json_string() {
    local value="${1:-}"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//$'\n'/\\n}"
    value="${value//$'\r'/\\r}"
    value="${value//$'\t'/\\t}"
    printf '"%s"' "$value"
}

agent_plan_run() {
    local plan="${1:-}"
    shift || true
    local confirm=0 arg

    while [[ $# -gt 0 ]]; do
        arg="$1"
        case "$arg" in
            --yes) confirm=1 ;;
            *)
                printf 'agent-run: unknown option: %s\n' "$arg" >&2
                return 2
                ;;
        esac
        shift
    done

    agent_plan_validate "$plan"

    if [[ "$AGENT_REQUIRE_CONFIRM" == "1" && "$confirm" -ne 1 ]]; then
        printf 'refusing to run without --yes; dry-run first, because fire is warm and files are mortal\n' >&2
        return 3
    fi

    bash "$plan"
}

agent_report_write() {
    local label="${1:-agent-report}"
    local outdir="$AGENT_ROOT/$AGENT_REPORT_DIR"
    local outfile="$outdir/$(agent_slug "$label").md"
    mkdir -p "$outdir"

    cat > "$outfile" <<REPORT
# Agentic CLI Report: $label

Generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)

## Profiles

\`\`\`text
$(agent_list_profiles)
\`\`\`

## Recent Tasks

\`\`\`text
$(find "$AGENT_ROOT/$AGENT_PLAN_DIR" -maxdepth 1 -type f 2>/dev/null | sort | tail -20)
\`\`\`

## Notes

This report is generated locally. No model provider, token stream, cloud ritual, or suspicious black box is required.
REPORT

    printf '%s\n' "$outfile"
}
