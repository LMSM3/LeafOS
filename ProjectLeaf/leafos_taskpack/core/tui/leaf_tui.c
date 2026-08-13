#define _POSIX_C_SOURCE 200809L

#include "leaf_tui_input.h"
#include "leaf_tui_pages.h"
#include "leaf_tui_state.h"

#include <locale.h>
#include <ncursesw/ncurses.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

typedef struct {
    const char *snapshot;
    const char *control_endpoint;
    const char *control_token;
    const char *message;
    int refresh_ms;
    int page;
    int plain;
    int width;
    int height;
} Options;

static void usage(FILE *stream) {
    fprintf(stream,
        "usage: leaf-tui --snapshot FILE [--control-endpoint HOST:PORT] [--control-token TOKEN]\n"
        "                [--message FILE]\n"
        "                [--refresh MS] [--page 1-7] [--plain] [--width N] [--height N]\n");
}

static int parse_options(int argc, char **argv, Options *options) {
    int index;
    memset(options, 0, sizeof(*options));
    options->refresh_ms = 250;
    options->width = 100;
    options->height = 30;
    for (index = 1; index < argc; index++) {
        if (strcmp(argv[index], "--snapshot") == 0 && index + 1 < argc) options->snapshot = argv[++index];
        else if (strcmp(argv[index], "--control-endpoint") == 0 && index + 1 < argc) options->control_endpoint = argv[++index];
        else if (strcmp(argv[index], "--control-token") == 0 && index + 1 < argc) options->control_token = argv[++index];
        else if (strcmp(argv[index], "--message") == 0 && index + 1 < argc) options->message = argv[++index];
        else if (strcmp(argv[index], "--refresh") == 0 && index + 1 < argc) options->refresh_ms = atoi(argv[++index]);
        else if (strcmp(argv[index], "--page") == 0 && index + 1 < argc) options->page = atoi(argv[++index]) - 1;
        else if (strcmp(argv[index], "--width") == 0 && index + 1 < argc) options->width = atoi(argv[++index]);
        else if (strcmp(argv[index], "--height") == 0 && index + 1 < argc) options->height = atoi(argv[++index]);
        else if (strcmp(argv[index], "--plain") == 0 || strcmp(argv[index], "--once") == 0) options->plain = 1;
        else if (strcmp(argv[index], "--help") == 0 || strcmp(argv[index], "-h") == 0) { usage(stdout); return 1; }
        else { fprintf(stderr, "leaf-tui: unknown or incomplete option: %s\n", argv[index]); return -1; }
    }
    if (!options->snapshot) {
        usage(stderr);
        return -1;
    }
    if (options->page < 0 || options->page > 6) options->page = 0;
    if (options->refresh_ms < 100) options->refresh_ms = 100;
    if (options->refresh_ms > 5000) options->refresh_ms = 5000;
    return 0;
}

static void read_message(const char *path, char *output, size_t output_size) {
    FILE *handle;
    size_t length;
    output[0] = '\0';
    if (!path) return;
    handle = fopen(path, "rb");
    if (!handle) return;
    length = fread(output, 1, output_size - 1, handle);
    fclose(handle);
    output[length] = '\0';
    while (length > 0 && (output[length - 1] == '\n' || output[length - 1] == '\r')) output[--length] = '\0';
}

static int safe_task_id(const char *value) {
    size_t index;
    size_t length;
    if (!value) return 0;
    length = strlen(value);
    if (length < 3 || length > 63 || !((value[0] >= 'A' && value[0] <= 'Z') || (value[0] >= 'a' && value[0] <= 'z'))) return 0;
    for (index = 1; index < length; index++) {
        char ch = value[index];
        if (!((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') || (ch >= '0' && ch <= '9') || ch == '.' || ch == '_' || ch == '-')) return 0;
    }
    return 1;
}

static int json_escape(const char *input, char *output, size_t output_size) {
    size_t source = 0;
    size_t target = 0;
    if (!input || !output || output_size == 0) return -1;
    while (input[source]) {
        unsigned char ch = (unsigned char)input[source++];
        if (ch < 32) return -1;
        if (ch == '"' || ch == '\\') {
            if (target + 2 >= output_size) return -1;
            output[target++] = '\\';
        } else if (target + 1 >= output_size) {
            return -1;
        }
        output[target++] = (char)ch;
    }
    output[target] = '\0';
    return 0;
}

static int socket_action(const char *endpoint, const char *token, const char *action, const char *task_id, int priority, const char *command) {
    char host[64];
    char payload[1024];
    char escaped_command[768];
    const char *separator;
    long port;
    char *port_end = NULL;
    size_t host_length;
    int sent = 0;
    int length;
    struct sockaddr_in address;
#ifdef _WIN32
    WSADATA data;
    SOCKET handle;
    if (WSAStartup(MAKEWORD(2, 2), &data) != 0) return -1;
#else
    int handle;
#endif
    if (!endpoint || !token || !action) {
#ifdef _WIN32
        WSACleanup();
#endif
        return -1;
    }
    separator = strrchr(endpoint, ':');
    if (!separator) goto failure;
    host_length = (size_t)(separator - endpoint);
    if (host_length == 0 || host_length >= sizeof(host)) goto failure;
    memcpy(host, endpoint, host_length);
    host[host_length] = '\0';
    if (strcmp(host, "127.0.0.1") != 0) goto failure;
    port = strtol(separator + 1, &port_end, 10);
    if (!port_end || *port_end != '\0' || port < 1 || port > 65535) goto failure;
    if (task_id && !safe_task_id(task_id)) goto failure;
    if (command) {
        if (strlen(command) > 512 || json_escape(command, escaped_command, sizeof(escaped_command)) != 0) goto failure;
        length = snprintf(payload, sizeof(payload), "{\"token\":\"%s\",\"action\":\"%s\",\"command\":\"%s\"}\n", token, action, escaped_command);
    } else if (task_id && priority >= 0) {
        length = snprintf(payload, sizeof(payload), "{\"token\":\"%s\",\"action\":\"%s\",\"task_id\":\"%s\",\"priority\":%d}\n", token, action, task_id, priority);
    } else if (task_id) {
        length = snprintf(payload, sizeof(payload), "{\"token\":\"%s\",\"action\":\"%s\",\"task_id\":\"%s\"}\n", token, action, task_id);
    } else {
        length = snprintf(payload, sizeof(payload), "{\"token\":\"%s\",\"action\":\"%s\"}\n", token, action);
    }
    if (length <= 0 || length >= (int)sizeof(payload)) goto failure;
    handle = socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
#ifdef _WIN32
    if (handle == INVALID_SOCKET) goto failure;
#else
    if (handle < 0) goto failure;
#endif
    memset(&address, 0, sizeof(address));
    address.sin_family = AF_INET;
    address.sin_port = htons((unsigned short)port);
    if (inet_pton(AF_INET, host, &address.sin_addr) != 1 || connect(handle, (struct sockaddr *)&address, sizeof(address)) != 0) goto socket_failure;
    while (sent < length) {
        int written = send(handle, payload + sent, length - sent, 0);
        if (written <= 0) goto socket_failure;
        sent += written;
    }
#ifdef _WIN32
    closesocket(handle);
    WSACleanup();
#else
    close(handle);
#endif
    return 0;

socket_failure:
#ifdef _WIN32
    closesocket(handle);
#else
    close(handle);
#endif
failure:
#ifdef _WIN32
    WSACleanup();
#endif
    return -1;
}

static int send_action(const Options *options, const char *action, const char *task_id, int priority, const char *command) {
    return socket_action(options->control_endpoint, options->control_token, action, task_id, priority, command);
}

static const char *action_name(LeafTuiAction action) {
    switch (action) {
        case LEAF_TUI_ACTION_PAUSE_TOGGLE: return "pause_toggle";
        case LEAF_TUI_ACTION_APPROVE: return "approve";
        case LEAF_TUI_ACTION_STOP: return "stop";
        case LEAF_TUI_ACTION_LIVE_COMMAND: return "live_command";
        case LEAF_TUI_ACTION_PROJECT_WIZARD: return NULL;
        case LEAF_TUI_ACTION_TASK_RETRY: return "task_retry";
        case LEAF_TUI_ACTION_TASK_CANCEL: return "task_cancel";
        case LEAF_TUI_ACTION_TASK_APPROVE: return "task_approve";
        case LEAF_TUI_ACTION_TASK_PRIORITY_UP:
        case LEAF_TUI_ACTION_TASK_PRIORITY_DOWN: return "task_prioritize";
        default: return NULL;
    }
}

int main(int argc, char **argv) {
    Options options;
    LeafTuiState *state;
    LeafTuiState *candidate;
    LeafTuiInput input;
    char error[256] = "";
    char external_message[256] = "";
    int refresh_failures = 0;
    int parsed = parse_options(argc, argv, &options);
    if (parsed != 0) return parsed > 0 ? 0 : 2;
    state = (LeafTuiState *)calloc(1, sizeof(*state));
    candidate = (LeafTuiState *)calloc(1, sizeof(*candidate));
    if (!state || !candidate) {
        free(state);
        free(candidate);
        fprintf(stderr, "leaf-tui: state allocation failed\n");
        return 2;
    }
    if (leaf_tui_state_load(options.snapshot, state, error, sizeof(error)) != 0) {
        fprintf(stderr, "leaf-tui: %s\n", error);
        free(state);
        free(candidate);
        return 2;
    }
    if (options.plain) {
        leaf_tui_pages_plain(state, options.page, options.width, options.height);
        free(state);
        free(candidate);
        return 0;
    }
    setlocale(LC_ALL, "");
    if (initscr() == NULL) {
        fprintf(stderr, "leaf-tui: terminal initialization failed; use --plain\n");
        free(state);
        free(candidate);
        return 2;
    }
    cbreak();
    noecho();
    keypad(stdscr, TRUE);
    curs_set(0);
    timeout(options.refresh_ms);
    leaf_tui_pages_init_colors();
    leaf_tui_input_init(&input, options.page);
    for (;;) {
        int key;
        LeafTuiAction action;
        if (!input.frozen && leaf_tui_state_load(options.snapshot, candidate, error, sizeof(error)) == 0) {
            LeafTuiState *swap = state;
            state = candidate;
            candidate = swap;
            refresh_failures = 0;
            read_message(options.message, external_message, sizeof(external_message));
        } else if (!input.frozen && ++refresh_failures >= 4) {
            snprintf(external_message, sizeof(external_message), "Snapshot refresh delayed: %.220s", error);
        }
        leaf_tui_pages_render(state, &input, external_message);
        key = getch();
        if (key == ERR || key == KEY_RESIZE) continue;
        action = leaf_tui_input_handle(&input, key);
        if (input.confirmation_mode == 2 && !input.confirmation_task_id[0] && state->task_count > 0) {
            int selected = input.selection < state->task_count ? input.selection : state->task_count - 1;
            snprintf(input.confirmation_task_id, sizeof(input.confirmation_task_id), "%s", state->tasks[selected].id);
        }
        if (action == LEAF_TUI_ACTION_QUIT) break;
        if (action == LEAF_TUI_ACTION_PROJECT_WIZARD) {
            endwin();
            free(state);
            free(candidate);
            return 20;
        }
        if (action != LEAF_TUI_ACTION_NONE) {
            const char *name = action_name(action);
            const char *task_id = NULL;
            const char *command_text = NULL;
            int priority = -1;
            if (action == LEAF_TUI_ACTION_LIVE_COMMAND) command_text = input.buffer;
            if (action >= LEAF_TUI_ACTION_TASK_RETRY) {
                int selected = input.selection < state->task_count ? input.selection : state->task_count - 1;
                if (selected >= 0) {
                    task_id = action == LEAF_TUI_ACTION_TASK_CANCEL && input.confirmation_task_id[0] ? input.confirmation_task_id : state->tasks[selected].id;
                    if (action == LEAF_TUI_ACTION_TASK_PRIORITY_UP) priority = state->tasks[selected].priority > 0 ? state->tasks[selected].priority - 1 : 0;
                    if (action == LEAF_TUI_ACTION_TASK_PRIORITY_DOWN) priority = state->tasks[selected].priority < 9 ? state->tasks[selected].priority + 1 : 9;
                }
            }
            if ((action < LEAF_TUI_ACTION_TASK_RETRY || task_id) && send_action(&options, name, task_id, priority, command_text) == 0) snprintf(input.message, sizeof(input.message), "%s request sent to inlet bridge.", name);
            else snprintf(input.message, sizeof(input.message), "Control bridge unavailable; no action sent.");
            if (action == LEAF_TUI_ACTION_LIVE_COMMAND) {
                input.buffer_length = 0;
                input.buffer[0] = '\0';
            }
            if (action == LEAF_TUI_ACTION_TASK_CANCEL) input.confirmation_task_id[0] = '\0';
        }
    }
    endwin();
    free(state);
    free(candidate);
    return 0;
}
