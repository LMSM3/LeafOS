#include "leaf_tui_input.h"

#include <ctype.h>
#include <ncursesw/ncurses.h>
#include <stdio.h>
#include <string.h>

void leaf_tui_input_init(LeafTuiInput *input, int page) {
    memset(input, 0, sizeof(*input));
    input->page = page >= 0 && page < 7 ? page : 0;
}

static void append_key(LeafTuiInput *input, int key) {
    if (key >= 0 && key <= 255 && isprint((unsigned char)key) && input->buffer_length + 1 < sizeof(input->buffer)) {
        input->buffer[input->buffer_length++] = (char)key;
        input->buffer[input->buffer_length] = '\0';
    }
}

static void backspace(LeafTuiInput *input) {
    if (input->buffer_length > 0) {
        input->buffer[--input->buffer_length] = '\0';
    }
}

LeafTuiAction leaf_tui_input_handle(LeafTuiInput *input, int key) {
    if (input->confirmation_mode) {
        if (key == 27) {
            input->confirmation_mode = 0;
            input->confirmation_task_id[0] = '\0';
            input->buffer_length = 0;
            input->buffer[0] = '\0';
            snprintf(input->message, sizeof(input->message), "Stop cancelled.");
        } else if (key == KEY_BACKSPACE || key == 127 || key == 8) {
            backspace(input);
        } else if (key == '\n' || key == '\r' || key == KEY_ENTER) {
            int confirmation = input->confirmation_mode;
            input->confirmation_mode = 0;
            if (confirmation == 1 && strcmp(input->buffer, "STOP") == 0) {
                input->buffer_length = 0;
                input->buffer[0] = '\0';
                return LEAF_TUI_ACTION_STOP;
            }
            if (confirmation == 2 && strcmp(input->buffer, "CANCEL") == 0) {
                input->buffer_length = 0;
                input->buffer[0] = '\0';
                return LEAF_TUI_ACTION_TASK_CANCEL;
            }
            snprintf(input->message, sizeof(input->message), "Confirmation did not match; no action taken.");
            input->confirmation_task_id[0] = '\0';
            input->buffer_length = 0;
            input->buffer[0] = '\0';
        } else {
            append_key(input, key);
        }
        return LEAF_TUI_ACTION_NONE;
    }
    if (input->command_mode) {
        if (key == 27) {
            input->command_mode = 0;
            input->buffer_length = 0;
            input->buffer[0] = '\0';
        } else if (key == KEY_BACKSPACE || key == 127 || key == 8) {
            backspace(input);
        } else if (key == '\n' || key == '\r' || key == KEY_ENTER) {
            input->command_mode = 0;
            if (strcmp(input->buffer, ":stop") == 0) {
                input->confirmation_mode = 1;
                input->buffer_length = 0;
                input->buffer[0] = '\0';
                snprintf(input->message, sizeof(input->message), "Type STOP and press Enter to stop the run.");
            } else if (input->buffer_length > 1) {
                return LEAF_TUI_ACTION_LIVE_COMMAND;
            } else {
                snprintf(input->message, sizeof(input->message), "Enter :improve, :again, :project, :new, or a plain objective.");
                input->buffer_length = 0;
                input->buffer[0] = '\0';
            }
        } else {
            append_key(input, key);
        }
        return LEAF_TUI_ACTION_NONE;
    }
    if (key == '\t') {
        input->page = (input->page + 1) % 7;
    } else if (key == KEY_BTAB) {
        input->page = (input->page + 6) % 7;
    } else if (key >= '1' && key <= '7') {
        input->page = key - '1';
    } else if (key == 'j' || key == KEY_DOWN) {
        input->selection++;
        input->scroll++;
    } else if (key == 'k' || key == KEY_UP) {
        if (input->selection > 0) input->selection--;
        if (input->scroll > 0) input->scroll--;
    } else if (key == ' ') {
        input->frozen = !input->frozen;
        snprintf(input->message, sizeof(input->message), "%s", input->frozen ? "View frozen; engine continues." : "Live view resumed.");
    } else if (key == 'l') {
        input->frozen = 0;
        input->scroll = 0;
        snprintf(input->message, sizeof(input->message), "Following live state.");
    } else if (key == '?') {
        input->help = !input->help;
    } else if (key == 'p') {
        return LEAF_TUI_ACTION_PAUSE_TOGGLE;
    } else if (key == 'a') {
        return LEAF_TUI_ACTION_APPROVE;
    } else if (key == 'A') {
        return LEAF_TUI_ACTION_TASK_APPROVE;
    } else if (key == 'r') {
        return LEAF_TUI_ACTION_TASK_RETRY;
    } else if (key == 'x') {
        input->confirmation_mode = 2;
        input->buffer_length = 0;
        input->buffer[0] = '\0';
        snprintf(input->message, sizeof(input->message), "Type CANCEL and press Enter to cancel the selected task.");
    } else if (key == '[') {
        return LEAF_TUI_ACTION_TASK_PRIORITY_UP;
    } else if (key == ']') {
        return LEAF_TUI_ACTION_TASK_PRIORITY_DOWN;
    } else if (key == 'n' || key == 'N') {
        return LEAF_TUI_ACTION_PROJECT_WIZARD;
    } else if (key == ':') {
        input->command_mode = 1;
        input->buffer[0] = ':';
        input->buffer[1] = '\0';
        input->buffer_length = 1;
    } else if (key == 'q' || key == 'Q') {
        return LEAF_TUI_ACTION_QUIT;
    }
    return LEAF_TUI_ACTION_NONE;
}

void leaf_tui_input_prompt(const LeafTuiInput *input, char *output, size_t output_size) {
    if (input->confirmation_mode) {
        snprintf(output, output_size, "Type %s to confirm: %s", input->confirmation_mode == 2 ? "CANCEL" : "STOP", input->buffer);
    } else if (input->command_mode) {
        snprintf(output, output_size, "%s", input->buffer);
    } else if (input->message[0]) {
        snprintf(output, output_size, "%s", input->message);
    } else if (input->help) {
        snprintf(output, output_size, "n new/open project | Live: :improve :mode :targets | Task: r retry x cancel A approve | q close");
    } else {
        snprintf(output, output_size, "Tab next | 1-7 page | ? help | q close interface");
    }
}
