#ifndef LEAF_TUI_INPUT_H
#define LEAF_TUI_INPUT_H

#include <stddef.h>

typedef enum {
    LEAF_TUI_ACTION_NONE = 0,
    LEAF_TUI_ACTION_QUIT,
    LEAF_TUI_ACTION_PAUSE_TOGGLE,
    LEAF_TUI_ACTION_APPROVE,
    LEAF_TUI_ACTION_STOP,
    LEAF_TUI_ACTION_LIVE_COMMAND,
    LEAF_TUI_ACTION_PROJECT_WIZARD,
    LEAF_TUI_ACTION_TASK_RETRY,
    LEAF_TUI_ACTION_TASK_CANCEL,
    LEAF_TUI_ACTION_TASK_APPROVE,
    LEAF_TUI_ACTION_TASK_PRIORITY_UP,
    LEAF_TUI_ACTION_TASK_PRIORITY_DOWN
} LeafTuiAction;

typedef struct {
    int page;
    int selection;
    int scroll;
    int frozen;
    int help;
    int command_mode;
    int confirmation_mode;
    char buffer[640];
    char confirmation_task_id[80];
    size_t buffer_length;
    char message[512];
} LeafTuiInput;

void leaf_tui_input_init(LeafTuiInput *input, int page);
LeafTuiAction leaf_tui_input_handle(LeafTuiInput *input, int key);
void leaf_tui_input_prompt(const LeafTuiInput *input, char *output, size_t output_size);

#endif
