#include "leaf_tui_state.h"
#include "leaf_tui_json.h"

#include <stdio.h>
#include <string.h>

static int member(const LeafJsonDoc *doc, int object, const char *key) {
    return leaf_json_object_get(doc, object, key);
}

static void copy_member(const LeafJsonDoc *doc, int object, const char *key, char *output, size_t size) {
    int token = member(doc, object, key);
    if (token >= 0) {
        leaf_json_copy(doc, token, output, size);
    }
}

static double number_member(const LeafJsonDoc *doc, int object, const char *key) {
    return leaf_json_number(doc, member(doc, object, key), -1.0);
}

static int integer_member(const LeafJsonDoc *doc, int object, const char *key, int fallback) {
    return (int)leaf_json_integer(doc, member(doc, object, key), fallback);
}

void leaf_tui_state_init(LeafTuiState *state) {
    memset(state, 0, sizeof(*state));
    snprintf(state->operator_name, sizeof(state->operator_name), "LeafOS");
    snprintf(state->engine_name, sizeof(state->engine_name), "LeafOS");
    state->gpu_percent = -1.0;
    state->vram_used_gb = -1.0;
    state->vram_total_gb = -1.0;
    state->gpu_temperature_c = -1.0;
    state->gpu_power_watts = -1.0;
    state->cpu_percent = -1.0;
    state->resident_cpu_target = -1.0;
    state->resident_gpu_target = -1.0;
    state->resident_cpu_headroom = -1.0;
    state->resident_gpu_headroom = -1.0;
    state->resident_input_idle_seconds = -1.0;
    state->resident_responsiveness_ms = -1.0;
    state->resident_elapsed_minutes = -1.0;
    state->ram_used_gb = -1.0;
    state->ram_total_gb = -1.0;
    state->brain_generation_tk_s = -1.0;
    state->brain_prompt_tk_s = -1.0;
    state->hardware_sample_age_seconds = -1.0;
    state->hardware_collection_seconds = -1.0;
    state->comparison_output_usd_per_million = -1.0;
    state->projected_gross_cloud_equivalent_usd_per_hour = -1.0;
}

static void parse_milestones(const LeafJsonDoc *doc, int array, LeafTuiState *state) {
    int count = leaf_json_array_size(doc, array);
    int index;
    if (count > 5) {
        count = 5;
    }
    for (index = 0; index < count; index++) {
        int object = leaf_json_array_get(doc, array, index);
        LeafTuiMilestone *milestone = &state->milestones[index];
        copy_member(doc, object, "name", milestone->name, sizeof(milestone->name));
        copy_member(doc, object, "state", milestone->state, sizeof(milestone->state));
        milestone->complete = integer_member(doc, object, "complete", 0);
        milestone->total = integer_member(doc, object, "total", 0);
    }
    state->milestone_count = count;
}

static void parse_tasks(const LeafJsonDoc *doc, int array, LeafTuiState *state) {
    int total = leaf_json_array_size(doc, array);
    int count = total > LEAF_TUI_MAX_TASKS ? LEAF_TUI_MAX_TASKS : total;
    int index;
    for (index = 0; index < count; index++) {
        int object = leaf_json_array_get(doc, array, index);
        LeafTuiTask *task = &state->tasks[index];
        copy_member(doc, object, "id", task->id, sizeof(task->id));
        copy_member(doc, object, "parent_id", task->parent_id, sizeof(task->parent_id));
        copy_member(doc, object, "kind", task->kind, sizeof(task->kind));
        copy_member(doc, object, "objective", task->objective, sizeof(task->objective));
        copy_member(doc, object, "status", task->status, sizeof(task->status));
        copy_member(doc, object, "symbol", task->symbol, sizeof(task->symbol));
        copy_member(doc, object, "role", task->role, sizeof(task->role));
        copy_member(doc, object, "model", task->model, sizeof(task->model));
        copy_member(doc, object, "worker", task->worker, sizeof(task->worker));
        copy_member(doc, object, "blocker", task->blocker, sizeof(task->blocker));
        task->priority = integer_member(doc, object, "priority", 2);
        task->correction_depth = integer_member(doc, object, "correction_depth", 0);
        task->attempts = integer_member(doc, object, "attempts", 0);
        task->max_attempts = integer_member(doc, object, "max_attempts", 1);
    }
    state->task_count = count;
    state->task_truncated = total > count ? total - count : 0;
}

static void parse_records(const LeafJsonDoc *doc, int array, LeafTuiRecord *records, int *count_out, int *truncated_out, int ledger) {
    int total = leaf_json_array_size(doc, array);
    int start = total > LEAF_TUI_MAX_STREAM ? total - LEAF_TUI_MAX_STREAM : 0;
    int index;
    int written = 0;
    for (index = start; index < total; index++, written++) {
        int object = leaf_json_array_get(doc, array, index);
        LeafTuiRecord *record = &records[written];
        record->sequence = leaf_json_integer(doc, member(doc, object, "sequence"), 0);
        copy_member(doc, object, "time", record->time, sizeof(record->time));
        copy_member(doc, object, ledger ? "type" : "category", record->category, sizeof(record->category));
        copy_member(doc, object, "task_id", record->task_id, sizeof(record->task_id));
        copy_member(doc, object, "summary", record->summary, sizeof(record->summary));
        copy_member(doc, object, "evidence", record->evidence, sizeof(record->evidence));
        record->durable = leaf_json_boolean(doc, member(doc, object, "durable"), ledger);
    }
    *count_out = written;
    *truncated_out = start;
}

static void add_result(LeafTuiState *state, const char *label, const char *detail, int passed) {
    LeafTuiResult *result;
    if (state->result_count >= LEAF_TUI_MAX_RESULTS) {
        state->result_truncated++;
        return;
    }
    result = &state->results[state->result_count++];
    snprintf(result->label, sizeof(result->label), "%s", label);
    snprintf(result->detail, sizeof(result->detail), "%s", detail);
    result->passed = passed;
}

static void parse_results(const LeafJsonDoc *doc, int object, LeafTuiState *state) {
    int array;
    int index;
    state->gate_ready = leaf_json_boolean(doc, member(doc, object, "gate_ready"), 0);
    array = member(doc, object, "validation");
    for (index = 0; index < leaf_json_array_size(doc, array); index++) {
        int item = leaf_json_array_get(doc, array, index);
        char label[LEAF_TUI_SHORT] = "validation";
        char detail[LEAF_TUI_TEXT] = "exit=?";
        long exit_code = leaf_json_integer(doc, member(doc, item, "exit_code"), -1);
        copy_member(doc, item, "step_id", label, sizeof(label));
        if (!label[0]) {
            copy_member(doc, item, "kind", label, sizeof(label));
        }
        snprintf(detail, sizeof(detail), "exit=%ld", exit_code);
        add_result(state, label, detail, exit_code == 0);
    }
    array = member(doc, object, "changed_files");
    for (index = 0; index < leaf_json_array_size(doc, array); index++) {
        int item = leaf_json_array_get(doc, array, index);
        char path[LEAF_TUI_TEXT] = "changed file";
        char hash[LEAF_TUI_TEXT] = "";
        copy_member(doc, item, "path", path, sizeof(path));
        copy_member(doc, item, "sha256", hash, sizeof(hash));
        add_result(state, "changed", path, 1);
    }
    array = member(doc, object, "artifacts");
    for (index = 0; index < leaf_json_array_size(doc, array); index++) {
        char path[LEAF_TUI_TEXT] = "";
        leaf_json_copy(doc, leaf_json_array_get(doc, array, index), path, sizeof(path));
        add_result(state, "artifact", path, 1);
    }
    array = member(doc, object, "failures");
    for (index = 0; index < leaf_json_array_size(doc, array); index++) {
        int item = leaf_json_array_get(doc, array, index);
        char task[LEAF_TUI_SHORT] = "failure";
        char summary[LEAF_TUI_TEXT] = "";
        copy_member(doc, item, "task_id", task, sizeof(task));
        copy_member(doc, item, "summary", summary, sizeof(summary));
        add_result(state, task, summary, 0);
    }
}

int leaf_tui_state_load(const char *snapshot_path, LeafTuiState *state, char *error, size_t error_size) {
    LeafJsonDoc doc;
    int root;
    int run;
    int operator;
    int benchmark;
    int work_order;
    int project;
    int resident;
    int queue;
    int hardware;
    int gpu;
    leaf_tui_state_init(state);
    if (leaf_json_load(snapshot_path, &doc, error, error_size) != 0) {
        return -1;
    }
    root = 0;
    operator = member(&doc, root, "operator");
    copy_member(&doc, operator, "name", state->operator_name, sizeof(state->operator_name));
    copy_member(&doc, operator, "engine", state->engine_name, sizeof(state->engine_name));
    copy_member(&doc, operator, "stage", state->operator_stage, sizeof(state->operator_stage));
    benchmark = member(&doc, root, "benchmark");
    copy_member(&doc, benchmark, "status", state->benchmark_status, sizeof(state->benchmark_status));
    state->benchmark_completed_cells = integer_member(&doc, benchmark, "completed_cells", 0);
    state->benchmark_planned_cells = integer_member(&doc, benchmark, "planned_cells", 0);
    hardware = member(&doc, benchmark, "comparison");
    state->comparison_output_usd_per_million = number_member(&doc, hardware, "comparison_output_usd_per_million");
    hardware = member(&doc, benchmark, "best_generation");
    state->projected_gross_cloud_equivalent_usd_per_hour = number_member(&doc, hardware, "projected_gross_cloud_equivalent_usd_per_hour");
    run = member(&doc, root, "run");
    copy_member(&doc, run, "id", state->run_id, sizeof(state->run_id));
    copy_member(&doc, run, "dir", state->run_dir, sizeof(state->run_dir));
    copy_member(&doc, run, "mode", state->mode, sizeof(state->mode));
    copy_member(&doc, run, "state", state->run_state, sizeof(state->run_state));
    copy_member(&doc, run, "elapsed", state->elapsed, sizeof(state->elapsed));
    copy_member(&doc, run, "safety", state->safety, sizeof(state->safety));
    copy_member(&doc, run, "checkpoint_age", state->checkpoint_age, sizeof(state->checkpoint_age));
    copy_member(&doc, run, "next_action", state->next_action, sizeof(state->next_action));
    state->accepting_tasks = leaf_json_boolean(&doc, member(&doc, run, "accepting_tasks"), 0);
    state->event_cursor = leaf_json_integer(&doc, member(&doc, root, "event_cursor"), 0);
    state->dropped_events = leaf_json_integer(&doc, member(&doc, root, "dropped_events"), 0);

    work_order = member(&doc, root, "work_order");
    copy_member(&doc, work_order, "id", state->work_order_id, sizeof(state->work_order_id));
    copy_member(&doc, work_order, "title", state->work_order_title, sizeof(state->work_order_title));
    copy_member(&doc, work_order, "objective", state->objective, sizeof(state->objective));
    project = member(&doc, root, "project");
    copy_member(&doc, project, "target", state->project_target, sizeof(state->project_target));
    copy_member(&doc, project, "state", state->project_state, sizeof(state->project_state));
    state->project_iteration = integer_member(&doc, project, "iteration", 0);
    state->project_catan2 = leaf_json_boolean(&doc, member(&doc, project, "catan2"), 0);
    resident = member(&doc, root, "resident");
    copy_member(&doc, resident, "status", state->resident_status, sizeof(state->resident_status));
    copy_member(&doc, resident, "mode", state->resident_mode, sizeof(state->resident_mode));
    copy_member(&doc, resident, "profile", state->resident_profile, sizeof(state->resident_profile));
    copy_member(&doc, resident, "reason", state->resident_reason, sizeof(state->resident_reason));
    state->resident_enabled = leaf_json_boolean(&doc, member(&doc, resident, "enabled"), 0);
    state->resident_supervisor_alive = leaf_json_boolean(&doc, member(&doc, resident, "supervisor_alive"), 0);
    state->resident_claim_allowed = leaf_json_boolean(&doc, member(&doc, resident, "claim_allowed"), 0);
    state->resident_supervisor_pid = leaf_json_integer(&doc, member(&doc, resident, "supervisor_pid"), 0);
    state->resident_cpu_slots = integer_member(&doc, resident, "cpu_slots", 0);
    hardware = member(&doc, resident, "targets");
    state->resident_cpu_target = number_member(&doc, hardware, "cpu_percent");
    state->resident_gpu_target = number_member(&doc, hardware, "gpu_percent");
    hardware = member(&doc, resident, "headroom");
    state->resident_cpu_headroom = number_member(&doc, hardware, "cpu_percent");
    state->resident_gpu_headroom = number_member(&doc, hardware, "gpu_percent");
    state->resident_input_idle_seconds = number_member(&doc, resident, "input_idle_seconds");
    state->resident_responsiveness_ms = number_member(&doc, resident, "responsiveness_ms");
    hardware = member(&doc, resident, "usage");
    state->resident_iterations = integer_member(&doc, hardware, "iterations_generated", 0);
    state->resident_elapsed_minutes = number_member(&doc, hardware, "elapsed_minutes");
    hardware = member(&doc, resident, "budgets");
    state->resident_max_iterations = integer_member(&doc, hardware, "max_iterations", 0);
    state->resident_budget_minutes = integer_member(&doc, hardware, "unattended_minutes", 0);
    parse_milestones(&doc, member(&doc, root, "milestones"), state);
    parse_tasks(&doc, member(&doc, root, "tasks"), state);

    queue = member(&doc, root, "queue");
    state->queue_waiting = integer_member(&doc, queue, "waiting", 0);
    state->queue_running = integer_member(&doc, queue, "running", 0);
    state->queue_blocked = integer_member(&doc, queue, "blocked", 0);

    hardware = member(&doc, root, "hardware");
    copy_member(&doc, hardware, "provider_health", state->provider_health, sizeof(state->provider_health));
    copy_member(&doc, hardware, "model", state->provider_model, sizeof(state->provider_model));
    copy_member(&doc, hardware, "stack_entry", state->stack_entry, sizeof(state->stack_entry));
    state->provider_pid = leaf_json_integer(&doc, member(&doc, hardware, "provider_pid"), 0);
    state->cpu_percent = number_member(&doc, hardware, "cpu_percent");
    state->ram_used_gb = number_member(&doc, hardware, "ram_used_gb");
    state->ram_total_gb = number_member(&doc, hardware, "ram_total_gb");
    state->brain_generation_tk_s = number_member(&doc, hardware, "brain_generation_tk_s");
    state->brain_prompt_tk_s = number_member(&doc, hardware, "brain_prompt_tk_s");
    state->hardware_live = leaf_json_boolean(&doc, member(&doc, hardware, "live"), 0);
    copy_member(&doc, hardware, "sampled_at", state->hardware_sampled_at, sizeof(state->hardware_sampled_at));
    state->hardware_sample_age_seconds = number_member(&doc, hardware, "sample_age_seconds");
    state->hardware_collection_seconds = number_member(&doc, hardware, "collection_seconds");
    gpu = member(&doc, hardware, "gpu");
    state->gpu_percent = number_member(&doc, gpu, "utilization_percent");
    state->vram_used_gb = number_member(&doc, gpu, "vram_used_gb");
    state->vram_total_gb = number_member(&doc, gpu, "vram_total_gb");
    state->gpu_temperature_c = number_member(&doc, gpu, "temperature_c");
    state->gpu_power_watts = number_member(&doc, gpu, "power_watts");

    hardware = member(&doc, root, "latest_validation");
    copy_member(&doc, hardware, "status", state->latest_validation_status, sizeof(state->latest_validation_status));
    copy_member(&doc, hardware, "summary", state->latest_validation_summary, sizeof(state->latest_validation_summary));
    parse_records(&doc, member(&doc, root, "brain"), state->brain, &state->brain_count, &state->brain_truncated, 0);
    parse_records(&doc, member(&doc, root, "ledger"), state->ledger, &state->ledger_count, &state->ledger_truncated, 1);
    parse_results(&doc, member(&doc, root, "results"), state);
    hardware = member(&doc, root, "control");
    copy_member(&doc, hardware, "transport", state->control_transport, sizeof(state->control_transport));
    state->control_authenticated = leaf_json_boolean(&doc, member(&doc, hardware, "authenticated"), 0);
    state->control_connected = leaf_json_boolean(&doc, member(&doc, hardware, "connected"), 0);
    gpu = member(&doc, hardware, "active_process");
    state->active_process_pid = leaf_json_integer(&doc, member(&doc, gpu, "pid"), 0);
    copy_member(&doc, gpu, "task_id", state->active_process_task_id, sizeof(state->active_process_task_id));
    leaf_json_free(&doc);
    return 0;
}
