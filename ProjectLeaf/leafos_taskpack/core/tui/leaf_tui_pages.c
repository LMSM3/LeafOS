#include "leaf_tui_pages.h"

#include <ncursesw/ncurses.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

enum { COLOR_NORMAL = 1, COLOR_RUNNING, COLOR_SUCCESS, COLOR_WARNING, COLOR_FAILURE, COLOR_MODEL };
static const char *PAGES[7] = {"Overview", "Tasks", "Hardware", "Queue", "Brain", "Ledger", "Results"};

static void draw_line(int row, int color, const char *format, ...) {
    char buffer[1024];
    va_list arguments;
    int height;
    int width;
    getmaxyx(stdscr, height, width);
    if (row < 0 || row >= height) return;
    va_start(arguments, format);
    vsnprintf(buffer, sizeof(buffer), format, arguments);
    va_end(arguments);
    attron(COLOR_PAIR(color));
    mvaddnstr(row, 0, buffer, width);
    attroff(COLOR_PAIR(color));
    clrtoeol();
}

static const char *metric(double value, const char *suffix, char *buffer, size_t size) {
    if (value < 0.0) snprintf(buffer, size, "n/a");
    else snprintf(buffer, size, "%.1f%s", value, suffix);
    return buffer;
}

static int status_color(const char *status) {
    if (strcmp(status, "complete") == 0 || strcmp(status, "passed") == 0) return COLOR_SUCCESS;
    if (strcmp(status, "failed") == 0) return COLOR_FAILURE;
    if (strcmp(status, "blocked") == 0 || strcmp(status, "repair_queued") == 0) return COLOR_WARNING;
    if (strcmp(status, "executing") == 0 || strcmp(status, "running") == 0) return COLOR_RUNNING;
    return COLOR_NORMAL;
}

void leaf_tui_pages_init_colors(void) {
    if (!has_colors()) return;
    start_color();
    use_default_colors();
    init_pair(COLOR_NORMAL, COLOR_WHITE, -1);
    init_pair(COLOR_RUNNING, COLOR_CYAN, -1);
    init_pair(COLOR_SUCCESS, COLOR_GREEN, -1);
    init_pair(COLOR_WARNING, COLOR_YELLOW, -1);
    init_pair(COLOR_FAILURE, COLOR_RED, -1);
    init_pair(COLOR_MODEL, COLOR_MAGENTA, -1);
}

static int draw_header(const LeafTuiState *state, int page) {
    char tabs[768] = "";
    char rail[512] = "";
    int index;
    int width = getmaxx(stdscr);
    if (state->dropped_events) {
        draw_line(0, strcmp(state->safety, "SAFE") == 0 ? COLOR_SUCCESS : COLOR_WARNING,
            "%s | %s engine | run %s | %s | %s | %s | checkpoint %s | DROPPED %ld",
            state->operator_name, state->engine_name, state->run_id, state->mode, state->elapsed, state->safety, state->checkpoint_age, state->dropped_events);
    } else {
        draw_line(0, strcmp(state->safety, "SAFE") == 0 ? COLOR_SUCCESS : COLOR_WARNING,
            "%s | %s engine | run %s | %s | %s | %s | checkpoint %s",
            state->operator_name, state->engine_name, state->run_id, state->mode, state->elapsed, state->safety, state->checkpoint_age);
    }
    for (index = 0; index < 7; index++) {
        char item[64];
        snprintf(item, sizeof(item), page == index ? "<%d %s> " : "[%d %s] ", index + 1, PAGES[index]);
        strncat(tabs, item, sizeof(tabs) - strlen(tabs) - 1);
    }
    draw_line(1, COLOR_NORMAL, "%s", tabs);
    for (index = 0; index < state->milestone_count; index++) {
        char item[80];
        const LeafTuiMilestone *milestone = &state->milestones[index];
        const char *symbol = strcmp(milestone->state, "complete") == 0 ? "+" : strcmp(milestone->state, "active") == 0 ? "*" : strcmp(milestone->state, "blocked") == 0 ? "!" : "o";
        snprintf(item, sizeof(item), "%s[%s %s]", index ? "--" : "", symbol, milestone->name);
        strncat(rail, item, sizeof(rail) - strlen(rail) - 1);
    }
    draw_line(2, COLOR_NORMAL, "%s", rail);
    draw_line(3, COLOR_NORMAL, "%.*s", width, "===============================================================================================================");
    return 4;
}

static const LeafTuiTask *active_task(const LeafTuiState *state) {
    int index;
    for (index = 0; index < state->task_count; index++) {
        const char *status = state->tasks[index].status;
        if (strcmp(status, "executing") == 0 || strcmp(status, "running") == 0 || strcmp(status, "repair_queued") == 0) return &state->tasks[index];
    }
    return state->task_count ? &state->tasks[state->task_count - 1] : NULL;
}

static void overview(const LeafTuiState *state, int row) {
    const LeafTuiTask *task = active_task(state);
    char gpu[32], vram[32], vram_total[32], brain[32], cpu[32];
    draw_line(row++, COLOR_NORMAL, "ACTIVE WORK");
    draw_line(row++, COLOR_MODEL, "PROJECT %s | %s | iteration %d", state->project_catan2 ? "CATAN2" : state->project_target, state->project_state, state->project_iteration);
    if (task) {
        draw_line(row++, status_color(task->status), "%s %s  %s", task->symbol, task->id, task->objective);
        draw_line(row++, COLOR_NORMAL, "  %s | %s | %s | attempts %d/%d", task->status, task->role, task->worker, task->attempts, task->max_attempts);
    } else draw_line(row++, COLOR_NORMAL, "No active task.");
    row++;
    draw_line(row++, COLOR_NORMAL, "SYSTEM SUMMARY");
    draw_line(row++, COLOR_NORMAL, "State %s | provider %s | PID %ld", state->run_state, state->provider_health, state->provider_pid);
    draw_line(row++, state->resident_supervisor_alive ? COLOR_SUCCESS : COLOR_WARNING, "Resident %s | %s | %s | PID %ld", state->resident_status, state->resident_profile, state->resident_reason, state->resident_supervisor_pid);
    draw_line(row++, state->control_connected ? COLOR_SUCCESS : COLOR_WARNING, "Control %s | authenticated %s", state->control_transport, state->control_authenticated ? "yes" : "no");
    draw_line(row++, state->active_process_pid ? COLOR_RUNNING : COLOR_NORMAL, "Child PID %ld | task %s", state->active_process_pid, state->active_process_task_id[0] ? state->active_process_task_id : "-");
    draw_line(row++, COLOR_NORMAL, "Queue %d waiting | %d running | %d blocked", state->queue_waiting, state->queue_running, state->queue_blocked);
    draw_line(row++, COLOR_RUNNING, "GPU %s | VRAM %s / %s | Brain %s | CPU %s",
        metric(state->gpu_percent, "%", gpu, sizeof(gpu)), metric(state->vram_used_gb, " GB", vram, sizeof(vram)),
        metric(state->vram_total_gb, " GB", vram_total, sizeof(vram_total)), metric(state->brain_generation_tk_s, " tk/s", brain, sizeof(brain)),
        metric(state->cpu_percent, "%", cpu, sizeof(cpu)));
    row++;
    draw_line(row++, COLOR_NORMAL, "LATEST");
    draw_line(row++, status_color(state->latest_validation_status), "TEST %s  %s", state->latest_validation_status, state->latest_validation_summary);
    draw_line(row++, COLOR_NORMAL, "NEXT %s", state->next_action);
    draw_line(row, COLOR_NORMAL, "PROJECT n new/open | LIVE :improve | :mode | :targets | :<objective>");
}

static void tasks(const LeafTuiState *state, const LeafTuiInput *input, int row, int height) {
    int index;
    int selected = input->selection < state->task_count ? input->selection : state->task_count - 1;
    int start = input->scroll < state->task_count ? input->scroll : selected;
    int available = height - row - 1;
    draw_line(row++, COLOR_NORMAL, "TASK GRAPH | root %s | %d tasks%s", state->work_order_id, state->task_count, state->task_truncated ? " (truncated)" : "");
    for (index = start; index < state->task_count && row < available; index++) {
        const LeafTuiTask *task = &state->tasks[index];
        draw_line(row++, status_color(task->status), "%c%c-- %s %s  %s", index == selected ? '>' : ' ', index == state->task_count - 1 ? '`' : '|', task->symbol, task->id, task->objective);
        if (row < available) draw_line(row++, COLOR_NORMAL, "    role=%s worker=%s attempts=%d/%d depth=%d", task->role, task->worker, task->attempts, task->max_attempts, task->correction_depth);
    }
}

static void hardware(const LeafTuiState *state, int row) {
    char gpu[32], used[32], total[32], generation[32], prompt[32], temperature[32], power[32], cpu[32], ram[32], ram_total[32], age[32], cpu_target[32], gpu_target[32], latency[32], local_value[32], comparison[32];
    draw_line(row++, state->hardware_live ? COLOR_SUCCESS : COLOR_WARNING, "HARDWARE | provider %s | %s sample %s", state->provider_health, state->hardware_live ? "live" : "recorded", metric(state->hardware_sample_age_seconds, "s old", age, sizeof(age)));
    row++;
    draw_line(row++, COLOR_MODEL, "GPU 0 | VULKAN | BRAIN STACK");
    draw_line(row++, COLOR_NORMAL, "Model        %s", state->provider_model);
    draw_line(row++, COLOR_NORMAL, "Stack        %s", state->stack_entry);
    draw_line(row++, COLOR_NORMAL, "Provider PID %ld", state->provider_pid);
    draw_line(row++, COLOR_RUNNING, "VRAM         %s / %s", metric(state->vram_used_gb, " GB", used, sizeof(used)), metric(state->vram_total_gb, " GB", total, sizeof(total)));
    draw_line(row++, COLOR_RUNNING, "Compute      %s", metric(state->gpu_percent, "%", gpu, sizeof(gpu)));
    draw_line(row++, COLOR_RUNNING, "Generation   %s", metric(state->brain_generation_tk_s, " tk/s", generation, sizeof(generation)));
    draw_line(row++, COLOR_RUNNING, "Prompt       %s", metric(state->brain_prompt_tk_s, " tk/s", prompt, sizeof(prompt)));
    draw_line(row++, COLOR_NORMAL, "Temperature  %s", metric(state->gpu_temperature_c, " C", temperature, sizeof(temperature)));
    draw_line(row++, COLOR_NORMAL, "Power        %s", metric(state->gpu_power_watts, " W", power, sizeof(power)));
    draw_line(row++, COLOR_NORMAL, "Benchmark    %s | %d/%d cells", state->benchmark_status, state->benchmark_completed_cells, state->benchmark_planned_cells);
    draw_line(row++, COLOR_NORMAL, "Local value  %s @ %s", metric(state->projected_gross_cloud_equivalent_usd_per_hour, " USD/h", local_value, sizeof(local_value)), metric(state->comparison_output_usd_per_million, " USD/M", comparison, sizeof(comparison)));
    row++;
    draw_line(row++, COLOR_NORMAL, "HOST");
    draw_line(row++, COLOR_NORMAL, "CPU          %s", metric(state->cpu_percent, "%", cpu, sizeof(cpu)));
    draw_line(row++, COLOR_NORMAL, "RAM          %s / %s", metric(state->ram_used_gb, " GB", ram, sizeof(ram)), metric(state->ram_total_gb, " GB", ram_total, sizeof(ram_total)));
    row++;
    draw_line(row++, COLOR_NORMAL, "RESIDENT %s | %s", state->resident_profile, state->resident_reason);
    draw_line(row++, COLOR_RUNNING, "Targets CPU %s | GPU %s | slots %d", metric(state->resident_cpu_target, "%", cpu_target, sizeof(cpu_target)), metric(state->resident_gpu_target, "%", gpu_target, sizeof(gpu_target)), state->resident_cpu_slots);
    draw_line(row, COLOR_NORMAL, "Input %.1fs idle | response %s", state->resident_input_idle_seconds, metric(state->resident_responsiveness_ms, " ms", latency, sizeof(latency)));
}

static void queue_page(const LeafTuiState *state, const LeafTuiInput *input, int row, int height) {
    int index;
    int selected = input->selection < state->task_count ? input->selection : state->task_count - 1;
    int start = input->scroll < state->task_count ? input->scroll : selected;
    draw_line(row++, COLOR_NORMAL, "QUEUE | %d waiting | %d running | policy DEPENDENCY + BOUNDED RETRY", state->queue_waiting, state->queue_running);
    draw_line(row++, COLOR_NORMAL, "RESIDENT %s | %s | iterations %d/%d | elapsed %.1f/%dm", state->resident_profile, state->resident_reason, state->resident_iterations, state->resident_max_iterations, state->resident_elapsed_minutes, state->resident_budget_minutes);
    draw_line(row++, COLOR_NORMAL, "POS STATE          PRI DEPTH ROLE       WORKER        TASK");
    for (index = start; index < state->task_count && row < height - 1; index++) {
        const LeafTuiTask *task = &state->tasks[index];
        draw_line(row++, status_color(task->status), "%c%3d %-14s P%d %5d %-10s %-13s %s %s", index == selected ? '>' : ' ', index + 1, task->status, task->priority, task->correction_depth, task->role, task->worker, task->id, task->objective);
    }
}

static void records_page(const LeafTuiRecord *records, int count, int truncated, const LeafTuiInput *input, int row, int height, int brain_page) {
    int available = height - row - 1;
    int start = count > available ? count - available : 0;
    int index;
    if (input->scroll > 0 && start > input->scroll) start -= input->scroll;
    draw_line(row++, brain_page ? COLOR_MODEL : COLOR_NORMAL, "%s | %d records%s", brain_page ? "BRAIN STREAM" : "LEDGER", count, truncated ? " (bounded tail)" : "");
    for (index = start; index < count && row < height - 1; index++) {
        const LeafTuiRecord *record = &records[index];
        const char *time = strlen(record->time) >= 19 ? record->time + 11 : record->time;
        draw_line(row++, brain_page ? COLOR_MODEL : COLOR_NORMAL, "%.8s %-18s %-12s %s%s", time, record->category, record->task_id, record->summary, brain_page && !record->durable ? " [transient]" : "");
    }
}

static void results_page(const LeafTuiState *state, const LeafTuiInput *input, int row, int height) {
    int index;
    draw_line(row++, state->gate_ready ? COLOR_SUCCESS : COLOR_WARNING, "RESULTS | gate status %s", state->gate_ready ? "READY" : "BLOCKED");
    for (index = input->scroll; index < state->result_count && row < height - 1; index++) {
        const LeafTuiResult *result = &state->results[index];
        draw_line(row++, result->passed ? COLOR_SUCCESS : COLOR_FAILURE, "%s %-16s %s", result->passed ? "+" : "!", result->label, result->detail);
    }
    if (!state->result_count) draw_line(row, COLOR_NORMAL, "No result evidence recorded.");
}

static void compact(const LeafTuiState *state) {
    const LeafTuiTask *task = active_task(state);
    char gpu[32], brain[32], cpu[32];
    draw_line(0, COLOR_NORMAL, "%s | %s engine | %s | %s | %s", state->operator_name, state->engine_name, state->run_id, state->run_state, state->safety);
    draw_line(1, COLOR_NORMAL, "1 Over 2 Task 3 HW 4 Queue 5 Brain 6 Ledg 7 Result");
    if (task) draw_line(3, status_color(task->status), "%s %s %s", task->symbol, task->id, task->objective);
    draw_line(4, COLOR_RUNNING, "GPU %s | %s | CPU %s", metric(state->gpu_percent, "%", gpu, sizeof(gpu)), metric(state->brain_generation_tk_s, " tk/s", brain, sizeof(brain)), metric(state->cpu_percent, "%", cpu, sizeof(cpu)));
    draw_line(5, COLOR_NORMAL, "Resident %s | %s", state->resident_profile, state->resident_reason);
    draw_line(6, COLOR_NORMAL, "Queue %d | Failed %d | checkpoint %s", state->queue_waiting, state->queue_blocked, state->checkpoint_age);
    draw_line(7, COLOR_NORMAL, "n new/open | Tab next | ? help | q quit");
}

void leaf_tui_pages_render(const LeafTuiState *state, const LeafTuiInput *input, const char *external_message) {
    int height;
    int width;
    int row;
    char prompt[256];
    getmaxyx(stdscr, height, width);
    erase();
    if (width < 80 || height < 24) {
        compact(state);
        refresh();
        return;
    }
    row = draw_header(state, input->page);
    switch (input->page) {
        case 0: overview(state, row); break;
        case 1: tasks(state, input, row, height); break;
        case 2: hardware(state, row); break;
        case 3: queue_page(state, input, row, height); break;
        case 4: records_page(state->brain, state->brain_count, state->brain_truncated, input, row, height, 1); break;
        case 5: records_page(state->ledger, state->ledger_count, state->ledger_truncated, input, row, height, 0); break;
        case 6: results_page(state, input, row, height); break;
    }
    leaf_tui_input_prompt(input, prompt, sizeof(prompt));
    draw_line(height - 1, COLOR_NORMAL, "%s", external_message && external_message[0] ? external_message : prompt);
    refresh();
}

void leaf_tui_pages_plain(const LeafTuiState *state, int page, int width, int height) {
    const LeafTuiTask *task = active_task(state);
    char cpu_target[32], gpu_target[32];
    (void)width;
    (void)height;
    printf("%s | %s engine | run %s | %s | %s | %s | checkpoint %s\n", state->operator_name, state->engine_name, state->run_id, state->mode, state->elapsed, state->safety, state->checkpoint_age);
    printf("Page %d %s | cursor %ld\n", page + 1, PAGES[page], state->event_cursor);
    printf("[INTAKE]--[PLAN]--[EXECUTE]--[VALIDATE]--[PUBLISH]\n");
    if (page == 2) {
        printf("HARDWARE | %s | sample %.3fs old\nModel %s\nGPU %.1f%% / %s target | VRAM %.1f/%.1f GB | Brain %.2f tk/s | CPU %.1f%% / %s target\nBenchmark %s | %d/%d cells | local value %.4f USD/h @ %.2f USD/M\nResident %s | %s\n", state->hardware_live ? "live" : "recorded", state->hardware_sample_age_seconds, state->provider_model, state->gpu_percent, metric(state->resident_gpu_target, "%", gpu_target, sizeof(gpu_target)), state->vram_used_gb, state->vram_total_gb, state->brain_generation_tk_s, state->cpu_percent, metric(state->resident_cpu_target, "%", cpu_target, sizeof(cpu_target)), state->benchmark_status, state->benchmark_completed_cells, state->benchmark_planned_cells, state->projected_gross_cloud_equivalent_usd_per_hour, state->comparison_output_usd_per_million, state->resident_profile, state->resident_reason);
    } else if (page == 6) {
        int index;
        printf("RESULTS | gate %s\n", state->gate_ready ? "READY" : "BLOCKED");
        for (index = 0; index < state->result_count; index++) printf("%c %s %s\n", state->results[index].passed ? '+' : '!', state->results[index].label, state->results[index].detail);
    } else {
        printf("WORK ORDER %s | %s\n", state->work_order_id, state->work_order_title);
        if (task) printf("ACTIVE %s %s | %s\n", task->id, task->objective, task->status);
        printf("Queue %d waiting | %d running | %d blocked\n", state->queue_waiting, state->queue_running, state->queue_blocked);
        printf("NEXT %s\n", state->next_action);
    }
}
