#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <math.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/statvfs.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#define MAX_ROWS 8
#define MAX_COLS 256
#define GLYPH_BYTES 5
#define TARGET_HZ 60.0
#define SAMPLE_HZ 4.0
#define PATH_BYTES 4096
#define VERSION_BYTES 64

typedef struct {
    char glyph[GLYPH_BYTES];
    uint8_t fg;
    uint8_t bg;
} Cell;

typedef struct {
    Cell cells[MAX_ROWS][MAX_COLS];
    int rows;
    int cols;
} Frame;

typedef struct {
    uint64_t total;
    uint64_t idle;
} CpuSample;

typedef struct {
    double used_percent;
    double available_gib;
} DiskSample;

static volatile sig_atomic_t running = 1;
static struct termios saved_termios;
static int saved_flags = -1;
static bool terminal_configured = false;

static void stop_monitor(int signal_number)
{
    (void)signal_number;
    running = 0;
}

static void restore_terminal(void)
{
    if (!terminal_configured)
        return;

    tcsetattr(STDIN_FILENO, TCSAFLUSH, &saved_termios);
    if (saved_flags >= 0)
        fcntl(STDIN_FILENO, F_SETFL, saved_flags);

    fputs("\x1b[0m\x1b[?25h\x1b[?1049l", stdout);
    fflush(stdout);
    terminal_configured = false;
}

static bool setup_terminal(void)
{
    struct termios raw;

    if (!isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO)) {
        errno = ENOTTY;
        return false;
    }

    if (tcgetattr(STDIN_FILENO, &saved_termios) != 0)
        return false;

    raw = saved_termios;
    raw.c_lflag &= (tcflag_t)~(ICANON | ECHO);
    raw.c_cc[VMIN] = 0;
    raw.c_cc[VTIME] = 0;
    if (tcsetattr(STDIN_FILENO, TCSAFLUSH, &raw) != 0)
        return false;

    saved_flags = fcntl(STDIN_FILENO, F_GETFL);
    if (saved_flags >= 0)
        fcntl(STDIN_FILENO, F_SETFL, saved_flags | O_NONBLOCK);

    terminal_configured = true;
    atexit(restore_terminal);
    fputs("\x1b[?1049h\x1b[?25l\x1b[2J", stdout);
    fflush(stdout);
    return true;
}

static double monotonic_seconds(void)
{
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (double)now.tv_sec + (double)now.tv_nsec / 1000000000.0;
}

static void sleep_until(double deadline)
{
    struct timespec target;
    target.tv_sec = (time_t)deadline;
    target.tv_nsec = (long)((deadline - (double)target.tv_sec) * 1000000000.0);

    while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &target, NULL) == EINTR &&
           running) {
    }
}

static bool read_cpu(CpuSample *sample)
{
    FILE *file = fopen("/proc/stat", "r");
    uint64_t user, nice, system, idle, iowait, irq, softirq, steal;
    int count;

    if (!file)
        return false;

    count = fscanf(file,
                   "cpu  %" SCNu64 " %" SCNu64 " %" SCNu64 " %" SCNu64
                   " %" SCNu64 " %" SCNu64 " %" SCNu64 " %" SCNu64,
                   &user, &nice, &system, &idle, &iowait, &irq, &softirq, &steal);
    fclose(file);
    if (count != 8)
        return false;

    sample->idle = idle + iowait;
    sample->total = user + nice + system + idle + iowait + irq + softirq + steal;
    return true;
}

static double cpu_percent(CpuSample previous, CpuSample current)
{
    uint64_t total_delta = current.total - previous.total;
    uint64_t idle_delta = current.idle - previous.idle;

    if (total_delta == 0 || idle_delta > total_delta)
        return 0.0;
    return 100.0 * (double)(total_delta - idle_delta) / (double)total_delta;
}

static bool read_memory(double *percent)
{
    FILE *file = fopen("/proc/meminfo", "r");
    char key[64];
    char unit[16];
    uint64_t value;
    uint64_t total = 0;
    uint64_t available = 0;

    if (!file)
        return false;

    while (fscanf(file, "%63s %lu %15s", key, &value, unit) == 3) {
        if (strcmp(key, "MemTotal:") == 0)
            total = value;
        else if (strcmp(key, "MemAvailable:") == 0)
            available = value;
        if (total && available)
            break;
    }
    fclose(file);

    if (total == 0 || available > total)
        return false;

    *percent = 100.0 * (double)(total - available) / (double)total;
    return true;
}

static bool read_disk(const char *root, DiskSample *sample)
{
    struct statvfs stats;
    long double block_size;
    long double total;
    long double available;

    if (statvfs(root, &stats) != 0)
        return false;

    block_size = stats.f_frsize ? (long double)stats.f_frsize
                                : (long double)stats.f_bsize;
    total = (long double)stats.f_blocks * block_size;
    available = (long double)stats.f_bavail * block_size;
    if (total <= 0.0L || available > total)
        return false;

    sample->used_percent = 100.0 * (double)((total - available) / total);
    sample->available_gib = (double)(available / (1024.0L * 1024.0L * 1024.0L));
    return true;
}

static void read_leafos_version(const char *root, char *version, size_t size)
{
    char path[PATH_BYTES];
    FILE *file;

    if (snprintf(path, sizeof(path), "%s/VERSION", root) >= (int)sizeof(path)) {
        snprintf(version, size, "%s", "unknown");
        return;
    }

    file = fopen(path, "r");
    if (!file || !fgets(version, (int)size, file)) {
        if (file)
            fclose(file);
        snprintf(version, size, "%s", "unknown");
        return;
    }
    fclose(file);

    version[strcspn(version, "\r\n")] = '\0';
    if (version[0] == '\0')
        snprintf(version, size, "%s", "unknown");
}

static int terminal_columns(void)
{
    struct winsize size;
    if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &size) == 0 && size.ws_col > 0)
        return size.ws_col > MAX_COLS ? MAX_COLS : size.ws_col;
    return 80;
}

static Cell blank_cell(void)
{
    Cell cell = {{' ', '\0'}, 250, 234};
    return cell;
}

static void clear_frame(Frame *frame, int rows, int cols)
{
    Cell blank = blank_cell();
    frame->rows = rows;
    frame->cols = cols;
    for (int row = 0; row < rows; ++row)
        for (int col = 0; col < cols; ++col)
            frame->cells[row][col] = blank;
}

static void put_cell(Frame *frame, int row, int col, const char *glyph,
                     uint8_t fg, uint8_t bg)
{
    Cell *cell;

    if (row < 0 || row >= frame->rows || col < 0 || col >= frame->cols)
        return;
    cell = &frame->cells[row][col];
    snprintf(cell->glyph, sizeof(cell->glyph), "%s", glyph);
    cell->fg = fg;
    cell->bg = bg;
}

static int put_text(Frame *frame, int row, int col, const char *text,
                    uint8_t fg, uint8_t bg)
{
    while (*text && col < frame->cols) {
        char glyph[2] = {*text++, '\0'};
        put_cell(frame, row, col++, glyph, fg, bg);
    }
    return col;
}

static uint8_t metric_color(double value)
{
    if (value > 80.0)
        return 196;
    if (value > 50.0)
        return 226;
    return 46;
}

static void draw_metric(Frame *frame, int row, const char *label, double value)
{
    static const char *fractions[] = {" ", "▂", "▃", "▄", "▅", "▆", "▇", "█"};
    char number[16];
    int col = 1;
    int fixed_width = 13;
    int bar_width = frame->cols - fixed_width - 2;
    double units;
    int full;
    int part;
    uint8_t color = metric_color(value);

    if (bar_width < 4)
        bar_width = 4;
    if (bar_width > 60)
        bar_width = 60;

    col = put_text(frame, row, col, label, 255, 234);
    col = put_text(frame, row, col, " ", 250, 234);
    snprintf(number, sizeof(number), "%5.1f%% ", value);
    col = put_text(frame, row, col, number, color, 234);
    col = put_text(frame, row, col, "[", 244, 234);

    units = value * (double)bar_width / 100.0;
    full = (int)units;
    part = (int)((units - (double)full) * 8.0);
    if (part < 0)
        part = 0;
    if (part > 7)
        part = 7;

    for (int index = 0; index < bar_width; ++index) {
        const char *glyph = " ";
        if (index < full)
            glyph = "█";
        else if (index == full && full < bar_width)
            glyph = fractions[part];
        put_cell(frame, row, col++, glyph, color, 234);
    }
    put_text(frame, row, col, "]", 244, 234);
}

static void draw_root(Frame *frame, int row, const char *root, double available_gib)
{
    char label[64];
    const char *visible_root = root;
    size_t root_length = strlen(root);
    int col;
    int available;

    snprintf(label, sizeof(label), "ROOT %7.1f GiB free // ", available_gib);
    col = put_text(frame, row, 1, label, 39, 234);
    available = frame->cols - col;
    if (available <= 0)
        return;

    if (root_length > (size_t)available && available > 3) {
        put_text(frame, row, col, "...", 250, 234);
        col += 3;
        visible_root = root + root_length - (size_t)(available - 3);
    }
    put_text(frame, row, col, visible_root, 250, 234);
}

static void build_frame(Frame *frame, double cpu, double memory, double disk,
                        double available_gib, const char *root, const char *version)
{
    char title[VERSION_BYTES + 64];
    int cols = terminal_columns();
    clear_frame(frame, 6, cols);
    snprintf(title, sizeof(title), "FLOWEROS // LEAFOS %s // HIGH-HZ MONITOR", version);
    put_text(frame, 0, 1, title, 208, 234);
    draw_metric(frame, 1, "CPU", cpu);
    draw_metric(frame, 2, "RAM", memory);
    draw_metric(frame, 3, "DSK", disk);
    draw_root(frame, 4, root, available_gib);
    put_text(frame, 5, 1, "q / Ctrl-C to exit", 244, 234);
}

static bool cells_equal(const Cell *left, const Cell *right)
{
    return left->fg == right->fg &&
           left->bg == right->bg &&
           strcmp(left->glyph, right->glyph) == 0;
}

static void render_diff(Frame *current, const Frame *next, bool force)
{
    int active_fg = -1;
    int active_bg = -1;
    bool cursor_known = false;
    int cursor_row = 0;
    int cursor_col = 0;

    for (int row = 0; row < next->rows; ++row) {
        for (int col = 0; col < next->cols; ++col) {
            const Cell *cell = &next->cells[row][col];
            bool changed = force || row >= current->rows || col >= current->cols ||
                           !cells_equal(&current->cells[row][col], cell);

            if (!changed)
                continue;

            if (!cursor_known || cursor_row != row || cursor_col != col) {
                printf("\x1b[%d;%dH", row + 1, col + 1);
                cursor_known = true;
            }
            if (active_fg != cell->fg || active_bg != cell->bg) {
                printf("\x1b[38;5;%dm\x1b[48;5;%dm", cell->fg, cell->bg);
                active_fg = cell->fg;
                active_bg = cell->bg;
            }
            fputs(cell->glyph, stdout);
            cursor_row = row;
            cursor_col = col + 1;
        }
    }

    if (force || current->rows != next->rows || current->cols != next->cols)
        printf("\x1b[%d;1H\x1b[0J", next->rows + 1);

    fflush(stdout);
    *current = *next;
}

static double smooth(double old_value, double new_value, double delta_time)
{
    const double response_seconds = 0.35;
    double alpha = 1.0 - exp(-delta_time / response_seconds);
    return old_value + alpha * (new_value - old_value);
}

static void print_usage(FILE *stream, const char *program)
{
    fprintf(stream,
            "usage: %s [--root PATH] [--once] [--json]\n"
            "       %s [--root PATH] --version\n"
            "\n"
            "60 Hz FlowerOS monitor for the canonical LeafOS root.\n"
            "The LEAFOS_ROOT environment variable supplies the default root.\n",
            program, program);
}

static void print_json_string(const char *value)
{
    const unsigned char *cursor = (const unsigned char *)value;

    fputc('"', stdout);
    while (*cursor) {
        switch (*cursor) {
        case '"':
            fputs("\\\"", stdout);
            break;
        case '\\':
            fputs("\\\\", stdout);
            break;
        case '\b':
            fputs("\\b", stdout);
            break;
        case '\f':
            fputs("\\f", stdout);
            break;
        case '\n':
            fputs("\\n", stdout);
            break;
        case '\r':
            fputs("\\r", stdout);
            break;
        case '\t':
            fputs("\\t", stdout);
            break;
        default:
            if (*cursor < 0x20)
                printf("\\u%04x", *cursor);
            else
                fputc(*cursor, stdout);
        }
        ++cursor;
    }
    fputc('"', stdout);
}

static int print_snapshot(const char *root, const char *version, bool as_json)
{
    CpuSample cpu_old;
    CpuSample cpu_new;
    DiskSample disk;
    double memory;
    double cpu;
    struct timespec delay = {0, 100000000L};

    if (!read_cpu(&cpu_old) || !read_memory(&memory) || !read_disk(root, &disk)) {
        fprintf(stderr, "flower: unable to read metrics for LeafOS root: %s\n", root);
        return EXIT_FAILURE;
    }
    while (nanosleep(&delay, &delay) != 0 && errno == EINTR) {
    }
    if (!read_cpu(&cpu_new)) {
        fputs("flower: unable to sample Linux CPU metrics\n", stderr);
        return EXIT_FAILURE;
    }
    cpu = cpu_percent(cpu_old, cpu_new);

    if (as_json) {
        fputs("{\"leafos_object\":\"leafos.flower_monitor_snapshot\","
              "\"schema_version\":1,\"leafos_version\":",
              stdout);
        print_json_string(version);
        fputs(",\"root\":", stdout);
        print_json_string(root);
        printf(",\"cpu_percent\":%.1f,\"memory_percent\":%.1f,"
               "\"disk_used_percent\":%.1f,\"disk_available_gib\":%.1f}\n",
               cpu, memory, disk.used_percent, disk.available_gib);
    } else {
        printf("FLOWEROS // LEAFOS %s\n"
               "ROOT  %s\n"
               "CPU   %5.1f%%\n"
               "RAM   %5.1f%%\n"
               "DISK  %5.1f%% used / %.1f GiB free\n",
               version, root, cpu, memory, disk.used_percent, disk.available_gib);
    }
    return EXIT_SUCCESS;
}

int main(int argc, char **argv)
{
    Frame current = {0};
    Frame next;
    CpuSample cpu_old;
    CpuSample cpu_new;
    DiskSample target_disk;
    const char *root = getenv("LEAFOS_ROOT");
    char version[VERSION_BYTES];
    bool once = false;
    bool as_json = false;
    bool show_version = false;
    double target_cpu = 0.0;
    double target_memory = 0.0;
    double shown_disk;
    double shown_cpu = 0.0;
    double shown_memory = 0.0;
    double frame_period = 1.0 / TARGET_HZ;
    double sample_period = 1.0 / SAMPLE_HZ;
    double next_frame;
    double next_sample;
    double previous_frame;
    int previous_cols = 0;

    if (!root || root[0] == '\0')
        root = ".";

    for (int index = 1; index < argc; ++index) {
        if (strcmp(argv[index], "--root") == 0) {
            if (++index >= argc) {
                fputs("flower: --root requires PATH\n", stderr);
                print_usage(stderr, argv[0]);
                return 2;
            }
            root = argv[index];
        } else if (strcmp(argv[index], "--once") == 0) {
            once = true;
        } else if (strcmp(argv[index], "--json") == 0) {
            once = true;
            as_json = true;
        } else if (strcmp(argv[index], "--version") == 0) {
            show_version = true;
        } else if (strcmp(argv[index], "--help") == 0 ||
                   strcmp(argv[index], "-h") == 0) {
            print_usage(stdout, argv[0]);
            return EXIT_SUCCESS;
        } else {
            fprintf(stderr, "flower: unknown option: %s\n", argv[index]);
            print_usage(stderr, argv[0]);
            return 2;
        }
    }

    read_leafos_version(root, version, sizeof(version));
    if (show_version) {
        puts(version);
        return EXIT_SUCCESS;
    }
    if (once)
        return print_snapshot(root, version, as_json);

    if (!setup_terminal()) {
        perror("flower: terminal setup");
        return EXIT_FAILURE;
    }

    signal(SIGINT, stop_monitor);
    signal(SIGTERM, stop_monitor);
    signal(SIGHUP, stop_monitor);

    if (!read_cpu(&cpu_old) || !read_memory(&target_memory) ||
        !read_disk(root, &target_disk)) {
        fprintf(stderr, "flower: unable to read metrics for LeafOS root: %s\n", root);
        return EXIT_FAILURE;
    }

    shown_memory = target_memory;
    shown_disk = target_disk.used_percent;
    previous_frame = monotonic_seconds();
    next_frame = previous_frame;
    next_sample = previous_frame + sample_period;

    while (running) {
        double now = monotonic_seconds();
        double delta_time = now - previous_frame;
        char key;

        while (read(STDIN_FILENO, &key, 1) == 1)
            if (key == 'q' || key == 'Q' || key == 3)
                running = 0;
        if (!running)
            break;

        if (now >= next_sample) {
            if (read_cpu(&cpu_new)) {
                target_cpu = cpu_percent(cpu_old, cpu_new);
                cpu_old = cpu_new;
            }
            read_memory(&target_memory);
            read_disk(root, &target_disk);
            do {
                next_sample += sample_period;
            } while (next_sample <= now);
        }

        shown_cpu = smooth(shown_cpu, target_cpu, delta_time);
        shown_memory = smooth(shown_memory, target_memory, delta_time);
        shown_disk = smooth(shown_disk, target_disk.used_percent, delta_time);
        build_frame(&next, shown_cpu, shown_memory, shown_disk,
                    target_disk.available_gib, root, version);

        bool resized = next.cols != previous_cols;
        render_diff(&current, &next, resized);
        previous_cols = next.cols;
        previous_frame = now;

        next_frame += frame_period;
        if (next_frame <= now)
            next_frame = now + frame_period;
        sleep_until(next_frame);
    }

    return EXIT_SUCCESS;
}
