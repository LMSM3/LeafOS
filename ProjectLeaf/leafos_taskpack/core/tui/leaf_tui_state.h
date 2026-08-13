#ifndef LEAF_TUI_STATE_H
#define LEAF_TUI_STATE_H

#include <stddef.h>

#define LEAF_TUI_MAX_TASKS 128
#define LEAF_TUI_MAX_STREAM 160
#define LEAF_TUI_MAX_RESULTS 96
#define LEAF_TUI_TEXT 256
#define LEAF_TUI_SHORT 80

typedef struct {
    char name[24];
    char state[16];
    int complete;
    int total;
} LeafTuiMilestone;

typedef struct {
    char id[LEAF_TUI_SHORT];
    char parent_id[LEAF_TUI_SHORT];
    char kind[32];
    char objective[LEAF_TUI_TEXT];
    char status[24];
    char symbol[8];
    char role[32];
    char model[LEAF_TUI_TEXT];
    char worker[64];
    char blocker[LEAF_TUI_TEXT];
    int priority;
    int correction_depth;
    int attempts;
    int max_attempts;
} LeafTuiTask;

typedef struct {
    long sequence;
    char time[40];
    char category[32];
    char task_id[LEAF_TUI_SHORT];
    char summary[LEAF_TUI_TEXT];
    char evidence[LEAF_TUI_TEXT];
    int durable;
} LeafTuiRecord;

typedef struct {
    char label[LEAF_TUI_SHORT];
    char detail[LEAF_TUI_TEXT];
    int passed;
} LeafTuiResult;

typedef struct {
    char operator_name[32];
    char engine_name[32];
    char operator_stage[32];
    char benchmark_status[32];
    char run_id[LEAF_TUI_SHORT];
    char run_dir[LEAF_TUI_TEXT];
    char mode[24];
    char run_state[24];
    char elapsed[24];
    char safety[24];
    char checkpoint_age[24];
    char next_action[LEAF_TUI_TEXT];
    char work_order_id[LEAF_TUI_SHORT];
    char work_order_title[LEAF_TUI_TEXT];
    char objective[LEAF_TUI_TEXT];
    char project_target[LEAF_TUI_TEXT];
    char project_state[32];
    char resident_status[32];
    char resident_mode[16];
    char resident_profile[32];
    char resident_reason[LEAF_TUI_TEXT];
    char provider_health[32];
    char provider_model[LEAF_TUI_TEXT];
    char stack_entry[LEAF_TUI_TEXT];
    char latest_validation_status[32];
    char latest_validation_summary[LEAF_TUI_TEXT];
    char hardware_sampled_at[40];
    char control_transport[32];
    char active_process_task_id[LEAF_TUI_SHORT];
    long event_cursor;
    long dropped_events;
    long provider_pid;
    long resident_supervisor_pid;
    long active_process_pid;
    int accepting_tasks;
    int project_iteration;
    int resident_enabled;
    int resident_supervisor_alive;
    int resident_claim_allowed;
    int resident_cpu_slots;
    int resident_iterations;
    int resident_max_iterations;
    int resident_budget_minutes;
    int hardware_live;
    int control_authenticated;
    int control_connected;
    int queue_waiting;
    int queue_running;
    int queue_blocked;
    int benchmark_completed_cells;
    int benchmark_planned_cells;
    double gpu_percent;
    double vram_used_gb;
    double vram_total_gb;
    double gpu_temperature_c;
    double gpu_power_watts;
    double cpu_percent;
    double resident_cpu_target;
    double resident_gpu_target;
    double resident_cpu_headroom;
    double resident_gpu_headroom;
    double resident_input_idle_seconds;
    double resident_responsiveness_ms;
    double resident_elapsed_minutes;
    double ram_used_gb;
    double ram_total_gb;
    double brain_generation_tk_s;
    double brain_prompt_tk_s;
    double hardware_sample_age_seconds;
    double hardware_collection_seconds;
    double comparison_output_usd_per_million;
    double projected_gross_cloud_equivalent_usd_per_hour;
    LeafTuiMilestone milestones[5];
    int milestone_count;
    LeafTuiTask tasks[LEAF_TUI_MAX_TASKS];
    int task_count;
    int task_truncated;
    LeafTuiRecord brain[LEAF_TUI_MAX_STREAM];
    int brain_count;
    int brain_truncated;
    LeafTuiRecord ledger[LEAF_TUI_MAX_STREAM];
    int ledger_count;
    int ledger_truncated;
    LeafTuiResult results[LEAF_TUI_MAX_RESULTS];
    int result_count;
    int result_truncated;
    int gate_ready;
} LeafTuiState;

void leaf_tui_state_init(LeafTuiState *state);
int leaf_tui_state_load(const char *snapshot_path, LeafTuiState *state, char *error, size_t error_size);

#endif
