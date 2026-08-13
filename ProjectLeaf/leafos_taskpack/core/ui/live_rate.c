/* live_rate.c -- close-to-the-metal terminal rate printer.
 *
 * Replacement for core/ui/live_stream.py's LiveRatePrinter.  EMA-smoothed
 * throughput, thinking/streaming phases, spinner, and TTY-aware in-place
 * refresh.  Depends only on the C standard library.
 */

#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <ctype.h>

#ifdef _WIN32
#include <windows.h>
#include <io.h>
#define isatty _isatty
#define fileno _fileno
#else
#include <unistd.h>
#include <sys/ioctl.h>
#endif

#ifndef LIVE_RATE_VERSION
#define LIVE_RATE_VERSION "1.0"
#endif

#define DEFAULT_REFRESH_MS 50
#define DEFAULT_EMA_ALPHA 0.35
#define SPIN_COUNT 8
#define MAX_TAIL 4096
#define ANSI_RESET  "\033[0m"
#define ANSI_DIM    "\033[2m"
#define ANSI_BOLD   "\033[1m"
#define ANSI_ACCENT "\033[1;36m"
#define ANSI_OK     "\033[1;32m"

static const char *SPIN_FRAMES[SPIN_COUNT] = {
	"\xE2\xA0\x8B", "\xE2\xA0\x99", "\xE2\xA0\xB8", "\xE2\xA0\xB4",
	"\xE2\xA0\xA6", "\xE2\xA0\xA7", "\xE2\xA0\x87", "\xE2\xA0\x8F"
};

static const char *RETURN_SYM = "\xE2\x8F\x8E";

struct lr_state {
	int is_tty;
	int use_color;
	int total_units;
	int last_unit_count;
	double ema_rate;
	double started;
	double first_unit_at;
	double last_refresh;
	int spin_idx;
	char tail[MAX_TAIL];
	size_t tail_len;
};

static double now_seconds(void) {
	struct timespec ts;
	if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
		return 0.0;
	}
	return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

static int terminal_width(void) {
#ifdef _WIN32
	CONSOLE_SCREEN_BUFFER_INFO csbi;
	HANDLE hOut = GetStdHandle(STD_OUTPUT_HANDLE);
	if (GetConsoleScreenBufferInfo(hOut, &csbi)) {
		return (int)(csbi.dwSize.X);
	}
#else
	struct winsize w;
	if (ioctl(STDOUT_FILENO, TIOCGWINSZ, &w) == 0 && w.ws_col > 0) {
		return (int)w.ws_col;
	}
#endif
	return 100;
}

static int visible_len(const char *s) {
	int len = 0;
	int skip = 0;
	for (const unsigned char *p = (const unsigned char *)s; *p; ++p) {
		if (*p == '\033') {
			skip = 1;
			continue;
		}
		if (skip) {
			if (isalpha((int)*p)) skip = 0;
			continue;
		}
		len++;
	}
	return len;
}

static const char *color_code(const char *name) {
	if (strcmp(name, "reset") == 0)  return ANSI_RESET;
	if (strcmp(name, "dim") == 0)    return ANSI_DIM;
	if (strcmp(name, "accent") == 0) return ANSI_ACCENT;
	if (strcmp(name, "ok") == 0)     return ANSI_OK;
	return "";
}

static const char *color(struct lr_state *st, const char *name) {
	if (!st || !st->use_color) return "";
	return color_code(name);
}

static void lr_init(struct lr_state *st) {
	memset(st, 0, sizeof(*st));
	st->is_tty = isatty(fileno(stdout));
	st->use_color = st->is_tty;
	st->started = now_seconds();
	st->last_refresh = 0.0;
	st->ema_rate = 0.0;
	st->tail[0] = '\0';
	st->tail_len = 0;
}

static void lr_update_text(struct lr_state *st, const char *text, int replace) {
	if (!text || !*text) return;
	if (replace) {
		st->tail_len = 0;
		st->tail[0] = '\0';
	}
	size_t len = strlen(text);
	if (len >= MAX_TAIL) {
		text += len - (MAX_TAIL - 1);
		len = MAX_TAIL - 1;
		st->tail_len = 0;
	}
	if (st->tail_len + len >= MAX_TAIL) {
		size_t keep = MAX_TAIL - len - 1;
		memmove(st->tail, st->tail + (st->tail_len - keep), keep + 1);
		st->tail_len = keep;
	}
	memcpy(st->tail + st->tail_len, text, len);
	st->tail_len += len;
	st->tail[st->tail_len] = '\0';
}

static double smooth_rate(double prev, double inst, double alpha, int first) {
	if (alpha < 0.01) alpha = 0.01;
	if (alpha > 1.0) alpha = 1.0;
	if (inst < 0.0) inst = 0.0;
	if (first) return inst;
	return alpha * inst + (1.0 - alpha) * prev;
}

static void lr_render(struct lr_state *st, const char *label,
					  const char *unit_label, int force,
					  double refresh_seconds, double ema_alpha) {
	double t = now_seconds();
	if (!force && (t - st->last_refresh) < refresh_seconds) return;

	double dt = t - (st->last_refresh > 0 ? st->last_refresh : st->started);
	if (dt <= 0) dt = 0.001;
	int delta = st->total_units - st->last_unit_count;
	double inst = (double)delta / dt;
	int first_sample = (st->last_unit_count == 0 && st->ema_rate == 0.0);
	st->ema_rate = smooth_rate(st->ema_rate, inst, ema_alpha, first_sample);
	st->last_unit_count = st->total_units;
	st->last_refresh = t;

	double elapsed = t - st->started;
	int width = terminal_width();
	const char *reset = color(st, "reset");
	const char *dim = color(st, "dim");
	const char *accent = color(st, "accent");
	const char *ok = color(st, "ok");

	char line[8192];
	if (st->total_units == 0) {
		const char *frame = SPIN_FRAMES[st->spin_idx % SPIN_COUNT];
		st->spin_idx++;
		snprintf(line, sizeof(line),
			"  %s%s%s %s%s...%s  %s%.1fs%s",
			ok, frame, reset,
			dim, label, reset,
			dim, elapsed, reset);
	} else {
		char meta[512];
		snprintf(meta, sizeof(meta),
			"  %s[%.1fs | %d units | %s%6.1f %s%s]%s",
			dim, elapsed, st->total_units,
			ok, st->ema_rate, unit_label, dim, reset);

		int meta_vis = visible_len(meta);
		int avail = width - meta_vis - 4;
		if (avail < 8) avail = 8;

		/* Sanitize newlines in tail. */
		char tail[MAX_TAIL * 2];
		size_t ti = 0;
		const char *p = st->tail;
		size_t start = (st->tail_len > (size_t)avail) ? st->tail_len - (size_t)avail : 0;
		for (size_t i = start; i < st->tail_len && ti < sizeof(tail) - 8; ++i, ++p) {
			if (st->tail[i] == '\n') {
				tail[ti++] = ' ';
				memcpy(tail + ti, RETURN_SYM, 3);
				ti += 3;
				tail[ti++] = ' ';
			} else {
				tail[ti++] = st->tail[i];
			}
		}
		tail[ti] = '\0';

		snprintf(line, sizeof(line), "  %s%s%s%s", accent, tail, reset, meta);
	}

	if (st->is_tty) {
		int vis = visible_len(line);
		if (vis < width) {
			size_t pad = (size_t)(width - vis);
			if (strlen(line) + pad < sizeof(line) - 1) {
				memset(line + strlen(line), ' ', pad);
				line[strlen(line) + pad] = '\0';
			}
		}
		printf("\r%s", line);
	} else {
		printf("%s\n", line);
	}
	fflush(stdout);
}

static void lr_finish(struct lr_state *st, const char *summary) {
	lr_render(st, "thinking", "u/s", 1, 0.0, 0.0);
	printf("\n");
	if (summary && *summary) {
		printf("%s\n", summary);
	}
	fflush(stdout);
}

static void usage(const char *prog) {
	fprintf(stderr,
		"Usage: %s [options]\n"
		"  --unit LABEL        unit label (default: tk/s)\n"
		"  --refresh MS        refresh interval in ms (default: 50)\n"
		"  --alpha N           EMA alpha 0..1 (default: 0.35)\n"
		"  --demo              run a short demo\n"
		"  --help              show this help\n",
		prog);
}

/* Demo: simulate a thinking phase then tokens streaming in. */
static int run_demo(void) {
	struct lr_state st;
	lr_init(&st);
	const char *sample =
		"The quick brown fox jumps over the lazy dog. "
		"Close-to-the-metal rate printing keeps stdout responsive. ";
	size_t sample_len = strlen(sample);

	lr_render(&st, "thinking", "tk/s", 1, 0.05, 0.35);
	double think_until = now_seconds() + 0.6;
	while (now_seconds() < think_until) {
		lr_render(&st, "thinking", "tk/s", 0, 0.05, 0.35);
		struct timespec ts = {0, 20 * 1000000};
		nanosleep(&ts, NULL);
	}

	double stream_until = now_seconds() + 1.5;
	size_t pos = 0;
	while (now_seconds() < stream_until) {
		char tok[8] = {0};
		size_t n = 1 + (pos % 5);
		if (pos + n > sample_len) pos = 0;
		memcpy(tok, sample + pos, n);
		lr_update_text(&st, tok, 0);
		st.total_units += 1;
		pos += n;
		lr_render(&st, "streaming", "tk/s", 0, 0.05, 0.35);
		struct timespec ts = {0, 30 * 1000000};
		nanosleep(&ts, NULL);
	}

	lr_finish(&st, "demo complete");
	return 0;
}

int main(int argc, char **argv) {
	const char *unit = "tk/s";
	int refresh_ms = DEFAULT_REFRESH_MS;
	double alpha = DEFAULT_EMA_ALPHA;
	int demo = 0;

	for (int i = 1; i < argc; ++i) {
		if (strcmp(argv[i], "--help") == 0) {
			usage(argv[0]);
			return 0;
		}
		if (strcmp(argv[i], "--demo") == 0) {
			demo = 1;
		} else if (strcmp(argv[i], "--unit") == 0 && i + 1 < argc) {
			unit = argv[++i];
		} else if (strcmp(argv[i], "--refresh") == 0 && i + 1 < argc) {
			refresh_ms = atoi(argv[++i]);
		} else if (strcmp(argv[i], "--alpha") == 0 && i + 1 < argc) {
			alpha = atof(argv[++i]);
		} else {
			fprintf(stderr, "unknown option: %s\n", argv[i]);
			usage(argv[0]);
			return 1;
		}
	}

	if (demo) {
		return run_demo();
	}

	/* Line-oriented mode: read text updates from stdin. */
	struct lr_state st;
	lr_init(&st);
	lr_render(&st, "thinking", unit, 1, refresh_ms / 1000.0, alpha);

	char buf[4096];
	while (fgets(buf, sizeof(buf), stdin)) {
		size_t len = strlen(buf);
		if (len > 0 && buf[len - 1] == '\n') {
			buf[len - 1] = '\0';
			--len;
		}
		if (len == 0) continue;
		lr_update_text(&st, buf, 0);
		st.total_units += 1;
		lr_render(&st, "streaming", unit, 0, refresh_ms / 1000.0, alpha);
	}

	lr_finish(&st, "");
	return 0;
}
